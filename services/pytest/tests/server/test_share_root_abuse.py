"""Share-root abuse: nothing outside the share root, or outside a share link's paths, can be reached.

Every entry point that turns user input into a filesystem path under
``share_root`` is attacked with the same set of escapes:

- ``..`` traversal (plain and percent-encoded in URLs),
- absolute paths,
- a sibling directory whose name starts with the share root's name (``share-evil``),
- a file symlink and a directory symlink inside the share root pointing outside.

Staff side: ``AssociatePathAction``, ``serve_data_file``, ``ShareDirectoryAction``,
the insider file browser, and the ``add-data_path`` API.
Public side (share-link token, no login): browse, rclone, WebDAV, and the shared
browser page/entries — these must also hide files inside the root that are not shared.

Leaks are detected by content and canary markers rather than file names, because
pages echo the requested path back. Each attack test has a positive control on the
same route, so a test cannot pass just by hitting the wrong URL.
"""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from server.core import config
from server.utils.file_browser import is_within_root

from ..db.create_units import create_project
from ._http import assert_form_invalid, auth, get, post_form

SECRET = "TOP-SECRET-CONTENT"
UNSHARED = "PRIVATE-UNSHARED-CONTENT"
CANARY = "canary-marker"  # only ever appears in listings, never in a request
SHARED = "shared report content"
PASSWD = "root:x:0:0"


@dataclass(frozen=True)
class Layout:
    tmp: Path
    root: Path


@pytest.fixture
def layout(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Layout:
    """Requests `client` so the app config exists before share_root is patched.

    tmp/
      outside-secret.txt            SECRET
      canary-marker-parent.txt      (visible only if the share root's parent is listed)
      outside-dir/
        inner-secret.txt            SECRET
        canary-marker-outside.txt
      share-evil/                   sibling sharing the root's name prefix
        evil.txt                    SECRET
        canary-marker-evil.txt
      share/                        <- share_root
        unshared.txt                UNSHARED
        shared/                     <- the only path a share link exposes
          report.txt                SHARED
          link-out    -> tmp/outside-secret.txt
          dir-out     -> tmp/outside-dir
    """
    (tmp_path / "outside-secret.txt").write_text(SECRET)
    (tmp_path / f"{CANARY}-parent.txt").write_text(SECRET)
    (tmp_path / "outside-dir").mkdir()
    (tmp_path / "outside-dir" / "inner-secret.txt").write_text(SECRET)
    (tmp_path / "outside-dir" / f"{CANARY}-outside.txt").write_text(SECRET)
    (tmp_path / "share-evil").mkdir()
    (tmp_path / "share-evil" / "evil.txt").write_text(SECRET)
    (tmp_path / "share-evil" / f"{CANARY}-evil.txt").write_text(SECRET)

    root = tmp_path / "share"
    (root / "shared").mkdir(parents=True)
    (root / "unshared.txt").write_text(UNSHARED)
    (root / "shared" / "report.txt").write_text(SHARED)
    (root / "shared" / "link-out").symlink_to(tmp_path / "outside-secret.txt")
    (root / "shared" / "dir-out").symlink_to(tmp_path / "outside-dir", target_is_directory=True)

    monkeypatch.setattr(config.settings.app_config, "share_root", str(root))
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "test")
    return Layout(tmp=tmp_path, root=root)


def assert_no_leak(response, *, unshared: bool = False) -> None:
    body = response.text
    assert SECRET not in body, f"outside-root file content leaked ({response.status_code})"
    assert CANARY not in body, f"outside-root directory listing leaked ({response.status_code})"
    assert PASSWD not in body, f"/etc/passwd leaked ({response.status_code})"
    if unshared:
        assert UNSHARED not in body, f"unshared file content leaked ({response.status_code})"


# Share-root-relative paths as a form/query value or a stored DataPath. "{tmp}" is the absolute tmp dir.
FILE_ESCAPES = [
    pytest.param("../outside-secret.txt", id="dotdot"),
    pytest.param("shared/../../outside-secret.txt", id="nested-dotdot"),
    pytest.param("../share-evil/evil.txt", id="sibling-prefix"),
    pytest.param("{tmp}/outside-secret.txt", id="absolute"),
    pytest.param("/etc/passwd", id="absolute-system"),
    pytest.param("shared/link-out", id="file-symlink-out"),
    pytest.param("shared/dir-out/inner-secret.txt", id="dir-symlink-out"),
]

DIR_ESCAPES = [
    pytest.param("..", id="dotdot"),
    pytest.param("../outside-dir", id="dotdot-dir"),
    pytest.param("shared/../../outside-dir", id="nested-dotdot"),
    pytest.param("../share-evil", id="sibling-prefix"),
    pytest.param("{tmp}/outside-dir", id="absolute"),
    pytest.param("/etc", id="absolute-system"),
    pytest.param("shared/dir-out", id="dir-symlink-out"),
]


def _fill(path: str, layout: Layout) -> str:
    return path.replace("{tmp}", layout.tmp.as_posix())


# URL path segments after the route prefix, as (id, segment, kind). "file" vectors
# target file content, "dir" vectors target a directory listing. Traversal is
# percent-encoded because HTTP clients normalise literal "..", but the server
# decodes it back before routing.
URL_ESCAPES = [
    ("encoded-dotdot", "%2e%2e/outside-secret.txt", "file"),
    ("encoded-slash", "..%2foutside-secret.txt", "file"),
    ("nested-encoded-dotdot", "shared/%2e%2e/%2e%2e/outside-secret.txt", "file"),
    ("sibling-prefix", "%2e%2e/share-evil/evil.txt", "file"),
    ("absolute", "%2f{tmp_q}/outside-secret.txt", "file"),
    ("absolute-system", "%2fetc%2fpasswd", "file"),
    ("file-symlink-out", "shared/link-out", "file"),
    ("dir-symlink-out", "shared/dir-out/inner-secret.txt", "file"),
    ("parent-listing", "%2e%2e", "dir"),
    ("encoded-slash-listing", "..%2f", "dir"),
    ("nested-dotdot-listing", "shared/%2e%2e/%2e%2e", "dir"),
    ("sibling-prefix-listing", "%2e%2e/share-evil", "dir"),
    ("absolute-listing", "%2f{tmp_q}", "dir"),
    ("absolute-dir-listing", "%2f{tmp_q}/outside-dir", "dir"),
    ("dir-symlink-out-listing", "shared/dir-out", "dir"),
]

# Inside the share root but not part of the share link.
URL_UNSHARED = [
    ("unshared-file", "unshared.txt", "file"),
    ("unshared-via-dotdot", "shared/%2e%2e/unshared.txt", "file"),
    ("unshared-via-encoded-slash", "shared%2f..%2funshared.txt", "file"),
]


def _fill_url(segment: str, layout: Layout) -> str:
    return segment.replace("{tmp_q}", quote(layout.tmp.as_posix().lstrip("/"), safe=""))


# ── Helper ──────────────────────────────────────────────────────────────────


def test_is_within_root(layout: Layout):
    root = layout.root
    assert is_within_root(root, "shared/report.txt")
    assert is_within_root(root, "")
    assert is_within_root(root, "shared/../unshared.txt")

    for path in ["../outside-secret.txt", "shared/../../outside-secret.txt", "../share-evil/evil.txt",
                 str(layout.tmp / "outside-secret.txt"), "/etc/passwd", "shared/link-out",
                 "shared/dir-out", "shared/dir-out/inner-secret.txt"]:
        assert not is_within_root(root, path), path


# ── Staff: AssociatePathAction ──────────────────────────────────────────────


@pytest.fixture
def project(session: SyncSession, user: models.User) -> models.Project:
    project = create_project(session, user)
    session.commit()
    return project


def _data_path_count(session: SyncSession, project: models.Project) -> int:
    session.expire_all()
    return session.count(Q.data_path.select(project_id=project.id))


def test_associate_path_control(client: TestClient, session: SyncSession, project, insider_token: str, layout: Layout):
    response = post_form(client, "/htmx/files/associate-path", {"project": project.id},
                         token=insider_token, params={"path": "shared/report.txt"})
    assert response.status_code == 204
    assert _data_path_count(session, project) == 1


@pytest.mark.parametrize("path", FILE_ESCAPES + DIR_ESCAPES)
def test_associate_path_rejects_escape(
    client: TestClient, session: SyncSession, project, insider_token: str, layout: Layout, path: str,
):
    response = post_form(client, "/htmx/files/associate-path", {"project": project.id},
                         token=insider_token, params={"path": _fill(path, layout)})
    assert response.status_code == 400
    assert _data_path_count(session, project) == 0


# ── Staff → client: serve_data_file ─────────────────────────────────────────


def _plant(session: SyncSession, project: models.Project, path: str) -> models.DataPath:
    """Store a DataPath directly, as if it had slipped past validation (or predates it)."""
    data_path = session.save(Q.data_path.create(path=path, type=C.DataPathType.CUSTOM, project=project), flush=True)
    session.commit()
    return data_path


def test_serve_data_file_control(client: TestClient, session: SyncSession, project, user_token: str, layout: Layout):
    data_path = _plant(session, project, "shared/report.txt")
    response = get(client, f"/htmx/files/serve-data-file/{data_path.id}", user_token)
    assert response.status_code == 200
    assert response.text == SHARED


@pytest.mark.parametrize("path", FILE_ESCAPES)
@pytest.mark.parametrize("viewer", ["project_owner", "insider"])
def test_serve_data_file_rejects_escape(
    client: TestClient, session: SyncSession, project, user_token: str, insider_token: str,
    layout: Layout, path: str, viewer: str,
):
    data_path = _plant(session, project, _fill(path, layout))
    token = user_token if viewer == "project_owner" else insider_token

    response = get(client, f"/htmx/files/serve-data-file/{data_path.id}", token)

    assert response.status_code == 403
    assert_no_leak(response)


def test_serve_data_file_rejects_symlink_retargeted_after_association(
    client: TestClient, session: SyncSession, project, user_token: str, insider_token: str, layout: Layout,
):
    """A symlink that was safe when associated is re-checked when served."""
    link = layout.root / "shared" / "latest"
    link.symlink_to(layout.root / "shared" / "report.txt")
    response = post_form(client, "/htmx/files/associate-path", {"project": project.id},
                         token=insider_token, params={"path": "shared/latest"})
    assert response.status_code == 204
    [data_path] = session.get_all(Q.data_path.select(project_id=project.id), limit=None)
    assert get(client, f"/htmx/files/serve-data-file/{data_path.id}", user_token).text == SHARED

    link.unlink()
    link.symlink_to(layout.tmp / "outside-secret.txt")

    response = get(client, f"/htmx/files/serve-data-file/{data_path.id}", user_token)
    assert response.status_code == 403
    assert_no_leak(response)


# ── Staff: ShareDirectoryAction ─────────────────────────────────────────────


def _share_directory(client: TestClient, token: str, directory_path: str):
    return post_form(client, "/htmx/files/share-directory", {
        "directory_path": directory_path,
        "recipients": "someone@example.com",
        "time_valid_min": str(60 * 24),
    }, token=token)


def test_share_directory_control(
    client: TestClient, session: SyncSession, insider: models.User, insider_token: str, fake_mailer, layout: Layout,
):
    response = _share_directory(client, insider_token, "shared")
    assert response.status_code in (200, 204), response.text
    [share_token] = session.get_all(Q.share_token.select(owner_id=insider.id), limit=None)
    assert [p.path for p in share_token.paths] == ["shared"]
    assert len(fake_mailer.sent) == 1


@pytest.mark.parametrize("path", DIR_ESCAPES)
def test_share_directory_rejects_escape(
    client: TestClient, session: SyncSession, insider: models.User, insider_token: str,
    fake_mailer, layout: Layout, path: str,
):
    response = _share_directory(client, insider_token, _fill(path, layout))

    assert_form_invalid(response)
    session.expire_all()
    assert session.count(Q.share_token.select(owner_id=insider.id)) == 0
    assert fake_mailer.sent == []


# ── Staff: insider file browser ─────────────────────────────────────────────


def test_insider_file_browser_control(client: TestClient, insider_token: str, layout: Layout):
    response = get(client, "/htmx/files/shared", insider_token)
    assert response.status_code == 200
    assert "report.txt" in response.text


@pytest.mark.parametrize("segment", [pytest.param(seg, id=vid) for vid, seg, kind in URL_ESCAPES if kind == "dir"])
def test_insider_file_browser_does_not_list_outside_root(
    client: TestClient, insider_token: str, layout: Layout, segment: str,
):
    response = get(client, f"/htmx/files/{_fill_url(segment, layout)}", insider_token)
    assert_no_leak(response)


# ── Staff API: add-data_path ────────────────────────────────────────────────


@pytest.fixture
def share_mapping(layout: Layout, monkeypatch: pytest.MonkeyPatch) -> None:
    # Real (host) path prefix -> share-root-relative key.
    monkeypatch.setattr(config.settings.app_config, "share_path_mapping", {"shared": (layout.root / "shared").as_posix()})


def _add_data_path(client: TestClient, token: str, project: models.Project, path: str):
    return client.post("/api/shares/add-data_path", json={"path": path, "project_id": project.id}, headers=auth(token))


def test_add_data_path_api_control(
    client: TestClient, session: SyncSession, project, insider_token: str, layout: Layout, share_mapping,
):
    response = _add_data_path(client, insider_token, project, (layout.root / "shared" / "report.txt").as_posix())
    assert response.status_code == 200, response.text
    assert _data_path_count(session, project) == 1


@pytest.mark.parametrize("path", [
    pytest.param("{root}/shared/../../outside-secret.txt", id="dotdot"),
    pytest.param("{root}/shared/../unshared.txt", id="dotdot-unmapped"),
    pytest.param("{tmp}/outside-secret.txt", id="absolute"),
    pytest.param("/etc/passwd", id="absolute-system"),
    pytest.param("{root}/shared/link-out", id="file-symlink-out"),
    pytest.param("{root}/shared/dir-out/inner-secret.txt", id="dir-symlink-out"),
    pytest.param("../outside-secret.txt", id="relative"),
])
def test_add_data_path_api_rejects_escape(
    client: TestClient, session: SyncSession, project, insider_token: str,
    layout: Layout, share_mapping, path: str,
):
    real_path = path.replace("{root}", layout.root.as_posix()).replace("{tmp}", layout.tmp.as_posix())

    response = _add_data_path(client, insider_token, project, real_path)

    assert response.status_code in (400, 404), response.text
    assert _data_path_count(session, project) == 0


# ── Public: share-link routes (no login) ────────────────────────────────────


@pytest.fixture
def share_link(session: SyncSession, user: models.User, layout: Layout) -> str:
    token = session.save(Q.share_token.create(owner=user, time_valid_min=60, paths=["shared"]), flush=True)
    session.commit()
    return token.uuid


# (id, method, route, kinds): "file" routes can serve content, "dir" routes can list.
PUBLIC_ROUTES = [
    ("browse", "GET", "/api/shares/browse/{token}/{path}", {"file", "dir"}),
    ("rclone", "GET", "/api/shares/rclone/{token}/{path}", {"file", "dir"}),
    ("page", "GET", "/files/share/browse/{token}/{path}", {"file"}),  # listing is lazy-loaded from "entries"
    ("entries", "GET", "/files/share/browse/{token}/entries/{path}", {"dir"}),
    ("webdav-get", "GET", "/api/webdav/{token}/{path}", {"file"}),
    ("webdav-head", "HEAD", "/api/webdav/{token}/{path}", {"file"}),
    ("webdav-propfind", "PROPFIND", "/api/webdav/{token}/{path}", {"file", "dir"}),
]


def _public_cases(vectors):
    return [
        pytest.param(method, route, segment, id=f"{rid}-{vid}")
        for rid, method, route, kinds in PUBLIC_ROUTES
        for vid, segment, kind in vectors
        if kind in kinds
    ]


def _public(client: TestClient, method: str, route: str, token: str, path: str):
    return client.request(method, route.format(token=token, path=path), headers={"Depth": "1"})


def _assert_public_rejected(response, method: str) -> None:
    assert_no_leak(response, unshared=True)
    assert "content-disposition" not in response.headers, "a file was served"
    if method in ("HEAD", "PROPFIND"):  # HEAD has no body; PROPFIND leaks metadata, not content
        assert response.status_code >= 400
        assert "<D:response>" not in response.text


@pytest.mark.parametrize("method,route", [pytest.param(m, r, id=rid) for rid, m, r, _ in PUBLIC_ROUTES])
def test_public_share_control(client: TestClient, share_link: str, method: str, route: str):
    """Each public route does expose the shared file (or list it), so the attack tests below are meaningful."""
    path = "shared" if route.endswith("entries/{path}") or method == "PROPFIND" else "shared/report.txt"
    response = _public(client, method, route, share_link, path)
    assert response.status_code in (200, 207), response.text
    if method != "HEAD":
        assert SHARED in response.text or "report.txt" in response.text


@pytest.mark.parametrize("method,route,segment", _public_cases(URL_ESCAPES))
def test_public_share_rejects_escape(
    client: TestClient, share_link: str, layout: Layout, method: str, route: str, segment: str,
):
    response = _public(client, method, route, share_link, _fill_url(segment, layout))
    _assert_public_rejected(response, method)


@pytest.mark.parametrize("method,route,segment", _public_cases(URL_UNSHARED))
def test_public_share_rejects_unshared_path_inside_root(
    client: TestClient, share_link: str, method: str, route: str, segment: str,
):
    response = _public(client, method, route, share_link, segment)
    _assert_public_rejected(response, method)


@pytest.mark.parametrize("method,route", [pytest.param(m, r, id=rid) for rid, m, r, kinds in PUBLIC_ROUTES if "dir" in kinds])
def test_public_share_root_listing_hides_unshared(client: TestClient, share_link: str, method: str, route: str):
    """Listing the share root through a link shows only the shared directory."""
    response = _public(client, method, route, share_link, "")
    assert response.status_code in (200, 207), response.text
    assert "shared" in response.text
    assert "unshared.txt" not in response.text
