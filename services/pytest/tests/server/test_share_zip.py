"""Share downloads as one zip: the file list the app hands to nginx's mod_zip (server/utils/share_zip.py).

nginx streams whatever the list names, following symlinks, so the list is the security boundary: these
tests pin what may appear in it. Escapes through URLs (`..`, absolute paths, sibling prefixes, links out of
the root) are covered for the zip route with every other share route in test_share_root_abuse.py, symlink
cycles in test_share_symlink_cycles.py.

    share/                      <- share_root
      unshared.txt
      other/                    shared by a second token only
        other.txt
      shared/                   <- the token's path
        report.txt
        nested/child.txt
        empty/
        .DS_Store, ._report.txt
"""
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from opengsync_db import SyncSession, models, queries as Q

from server.core import config, dependencies
from server.utils import share_zip
from server.utils.shared_file_browser import SharedFileBrowser

ZIP_HEADERS = {"X-Archive-Support": "zip"}
LINE = re.compile(r"(?P<crc>-|0) (?P<size>\d+) (?P<location>\S+) (?P<name>.+)")


@dataclass(frozen=True)
class ZipShare:
    token: models.ShareToken
    root: Path


@pytest.fixture
def share_root(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Requests `client` so the app config exists before share_root is patched."""
    root = tmp_path / "share"
    shared = root / "shared"
    (shared / "nested").mkdir(parents=True)
    (shared / "empty").mkdir()
    (shared / "report.txt").write_text("report")
    (shared / "nested" / "child.txt").write_text("child")
    (shared / ".DS_Store").write_text("junk")
    (shared / "._report.txt").write_text("junk")
    (root / "unshared.txt").write_text("private")
    (root / "other").mkdir()
    (root / "other" / "other.txt").write_text("other")
    monkeypatch.setattr(config.settings.app_config, "share_root", str(root))
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "test")
    return root


@pytest.fixture
def zip_share(session: SyncSession, user: models.User, share_root: Path) -> ZipShare:
    token = session.save(Q.share_token.create(owner=user, time_valid_min=60, paths=["shared"]), flush=True)
    session.commit()
    return ZipShare(token=token, root=share_root)


def _browser(root: Path, paths: list[str]) -> SharedFileBrowser:
    return SharedFileBrowser(root, paths, cache_key=f"zip-test:{'|'.join(paths)}")


def assert_list_invariants(body: str, root: Path, shared: list[str]) -> list[tuple[str, str]]:
    """Every line of a file list is safe for nginx to serve and for an extractor to unpack.
    Returns (location, name) of each file."""
    shared_real = [Path(os.path.realpath(root / path)) for path in shared]
    files = []
    for line in body.splitlines():
        match = LINE.fullmatch(line)
        assert match is not None, f"malformed line {line!r}"
        name = match["name"]
        assert not name.startswith("/") and "\\" not in name and ":" not in name, name
        assert all(part not in ("", ".", "..") for part in name.removesuffix("/").split("/")), name
        assert not re.search(r"[\x00-\x1f\x7f]", name), name
        if match["location"] == "@directory":
            assert (match["crc"], match["size"]) == ("0", "0") and name.endswith("/"), line
            continue
        location = match["location"]
        assert match["crc"] == "-", line
        assert location.startswith("/nginx-share/"), line
        decoded = unquote(location)
        assert all(part not in (".", "..") for part in decoded.split("/")), line
        real = Path(os.path.realpath(root / decoded.removeprefix("/nginx-share/").lstrip("/")))
        assert real.is_relative_to(root.resolve()), f"{line} resolves outside the share root"
        assert real.is_file() and real.stat().st_size == int(match["size"]), line
        files.append((location, name))
    return files


def _names(manifest: share_zip.ZipManifest | None) -> list[str]:
    assert manifest is not None
    return [line.split(" ", 3)[3] for line in manifest.body.splitlines()]


# ── the route ───────────────────────────────────────────────────────────────


def test_zip_list_and_headers(client: TestClient, zip_share: ZipShare):
    response = client.get(f"/api/shares/zip/{zip_share.token.uuid}", headers=ZIP_HEADERS)
    assert response.status_code == 200, response.text
    assert response.headers["x-archive-files"] == "zip"
    assert response.headers["content-disposition"] == 'attachment; filename="BSF_DATA.zip"'
    assert re.fullmatch(r'"[0-9a-f]{32}"', response.headers["etag"])
    assert response.headers["last-modified"].endswith(" GMT")
    files = assert_list_invariants(response.text, zip_share.root, ["shared"])
    assert [name for _, name in files] == ["shared/nested/child.txt", "shared/report.txt"]
    assert response.text.splitlines() == [
        "0 0 @directory shared/empty/",
        "0 0 @directory shared/nested/",
        f"- 5 {files[0][0]} shared/nested/child.txt",
        f"- 6 {files[1][0]} shared/report.txt",
    ]


def test_folder_zip_starts_at_the_folder(client: TestClient, zip_share: ZipShare):
    response = client.get(f"/api/shares/zip/{zip_share.token.uuid}/shared/nested", headers=ZIP_HEADERS)
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == 'attachment; filename="nested.zip"'
    assert [name for _, name in assert_list_invariants(response.text, zip_share.root, ["shared"])] == ["nested/child.txt"]


def test_head_runs_the_same_checks(client: TestClient, zip_share: ZipShare):
    token = zip_share.token.uuid
    ok = client.head(f"/api/shares/zip/{token}", headers=ZIP_HEADERS)
    assert ok.status_code == 200
    assert ok.headers["etag"] == client.get(f"/api/shares/zip/{token}", headers=ZIP_HEADERS).headers["etag"]
    assert client.head(f"/api/shares/zip/{token}").status_code == 404
    assert client.head(f"/api/shares/zip/{token}/other", headers=ZIP_HEADERS).status_code == 404


def test_etag_is_stable_and_follows_the_files(client: TestClient, zip_share: ZipShare):
    url = f"/api/shares/zip/{zip_share.token.uuid}"
    first = client.get(url, headers=ZIP_HEADERS).headers["etag"]
    assert client.get(url, headers=ZIP_HEADERS).headers["etag"] == first

    report = zip_share.root / "shared" / "report.txt"
    stat = report.stat()
    report.write_text("report")  # same content and size
    os.utime(report, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert client.get(url, headers=ZIP_HEADERS).headers["etag"] != first, "a newer mtime must change the zip's identity"


def test_without_the_nginx_header_nothing_is_listed(client: TestClient, zip_share: ZipShare):
    for headers in ({}, {"X-Archive-Support": "yes"}, {"X-Archive-Support": "ZIP "}):
        response = client.get(f"/api/shares/zip/{zip_share.token.uuid}", headers=headers)
        assert response.status_code == 404, headers
        assert "x-archive-files" not in response.headers
        assert "report.txt" not in response.text


def test_browse_page_offers_zip_only_behind_nginx(client: TestClient, zip_share: ZipShare):
    url = f"/api/shares/browse/{zip_share.token.uuid}/shared"
    plain = client.get(url)
    assert plain.status_code == 200
    assert "/api/shares/zip/" not in plain.text

    behind_nginx = client.get(url, headers=ZIP_HEADERS)
    assert f"/api/shares/zip/{zip_share.token.uuid}\"" in behind_nginx.text  # Download all
    assert f"/api/shares/zip/{zip_share.token.uuid}/shared/nested\"" in behind_nginx.text  # folder row
    assert "/shared/report.txt\" download" not in behind_nginx.text  # no zip link on files


def test_unknown_and_expired_tokens_are_refused(client: TestClient, session: SyncSession, user: models.User, zip_share: ZipShare):
    assert client.get("/api/shares/zip/not-a-token", headers=ZIP_HEADERS).status_code == 404

    expired = session.save(Q.share_token.create(owner=user, time_valid_min=60, paths=["shared"]), flush=True)
    expired._expired = True
    session.save(expired)
    session.commit()
    for url in (f"/api/shares/zip/{expired.uuid}", f"/api/shares/zip/{expired.uuid}/shared"):
        response = client.get(url, headers=ZIP_HEADERS)
        assert response.status_code == 403
        assert "x-archive-files" not in response.headers


def test_another_tokens_paths_are_never_listed(client: TestClient, session: SyncSession, user: models.User, zip_share: ZipShare):
    other = session.save(Q.share_token.create(owner=user, time_valid_min=60, paths=["other"]), flush=True)
    session.commit()

    mine = client.get(f"/api/shares/zip/{zip_share.token.uuid}", headers=ZIP_HEADERS)
    assert "other" not in mine.text and "unshared" not in mine.text
    assert client.get(f"/api/shares/zip/{zip_share.token.uuid}/other", headers=ZIP_HEADERS).status_code == 404
    theirs = client.get(f"/api/shares/zip/{other.uuid}", headers=ZIP_HEADERS)
    assert [name for _, name in assert_list_invariants(theirs.text, zip_share.root, ["other"])] == ["other/other.txt"]
    assert "report" not in theirs.text


@pytest.mark.parametrize("subpath", [
    pytest.param("", id="share-root-listing"),  # the whole share: a control, see below
    pytest.param("shared/report.txt", id="a-file"),
    pytest.param("shared/missing", id="missing"),
    pytest.param("shared/empty", id="empty-folder"),
    pytest.param("unshared.txt", id="unshared-file"),
    pytest.param("other", id="unshared-folder"),
])
def test_folder_zip_must_be_a_shared_folder_with_files(client: TestClient, zip_share: ZipShare, subpath: str):
    response = client.get(f"/api/shares/zip/{zip_share.token.uuid}/{subpath}", headers=ZIP_HEADERS)
    if subpath == "":
        assert response.status_code == 200
        return
    assert response.status_code == 404, response.text
    assert "x-archive-files" not in response.headers


def test_folder_above_a_shared_path_is_refused(client: TestClient, session: SyncSession, user: models.User, share_root: Path):
    """Browse may open the folders above a shared path to navigate; a zip may not start there. nginx turns
    `deep/shared/%2e%2e` into `deep` before the app sees it, so this is reachable from a URL."""
    (share_root / "deep" / "shared").mkdir(parents=True)
    (share_root / "deep" / "shared" / "x.txt").write_text("x")
    (share_root / "deep" / "sibling.txt").write_text("sibling")
    token = session.save(Q.share_token.create(owner=user, time_valid_min=60, paths=["deep/shared"]), flush=True)
    session.commit()
    assert client.get(f"/api/shares/browse/{token.uuid}/deep").status_code == 200  # control: browse allows it
    response = client.get(f"/api/shares/zip/{token.uuid}/deep", headers=ZIP_HEADERS)
    assert response.status_code == 404
    assert "x-archive-files" not in response.headers


def _dependency_calls(dependant):
    yield dependant.call
    for dependency in dependant.dependencies:
        yield from _dependency_calls(dependency)


def test_route_is_audited_and_rate_limited(client: TestClient):
    from .test_route_sweep import _routes

    routes = [route for _, route in _routes(client.app.routes) if route.name == "file_share.zip"]
    assert len(routes) == 2  # with and without a subpath
    for route in routes:
        calls = set(_dependency_calls(route.dependant))
        assert dependencies.audit_share_access in calls
        assert dependencies.load_share_token in calls
        assert any("rate_limit" in getattr(call, "__qualname__", "") for call in calls), "the share rate limit is missing"
        assert route.methods == {"GET", "HEAD"}


# ── the file list (unit) ────────────────────────────────────────────────────


def test_list_injection_through_a_file_name_is_skipped(share_root: Path):
    """mod_zip reads one entry per line: a name with a line break could add an entry of its own. (A file name
    can't contain "/", so a forged location can't be spelled out; a forged entry can.)"""
    shared = share_root / "shared"
    (shared / "x\n0 0 @directory injected").write_text("evil")
    (shared / "carriage\rreturn.txt").write_text("evil")
    (shared / f"unicode{chr(0x2028)}break.txt").write_text("evil")  # a Unicode line separator
    manifest = share_zip.build_manifest(_browser(share_root, ["shared"]))
    assert manifest is not None
    assert "injected" not in manifest.body and "return.txt" not in manifest.body and "break.txt" not in manifest.body
    assert _names(manifest) == ["shared/empty/", "shared/nested/", "shared/nested/child.txt", "shared/report.txt"]
    assert_list_invariants(manifest.body, share_root, ["shared"])


@pytest.mark.parametrize("name,kept", [
    pytest.param("a\\..\\..\\evil.txt", False, id="backslash-traversal"),  # a separator on Windows
    pytest.param("C:evil.txt", False, id="drive-letter"),
    pytest.param("..foo", True, id="leading-dots"),
    pytest.param("foo..", True, id="trailing-dots"),
    pytest.param("...", True, id="three-dots"),
    pytest.param(" spaced name .txt", True, id="spaces"),
    pytest.param("Größe ü.txt", True, id="non-ascii"),
])
def test_names_that_extractors_could_misread_are_skipped(share_root: Path, name: str, kept: bool):
    (share_root / "shared" / name).write_text("x")
    manifest = share_zip.build_manifest(_browser(share_root, ["shared"]))
    files = assert_list_invariants(manifest.body, share_root, ["shared"])
    assert (f"shared/{name}" in [n for _, n in files]) is kept


def test_percent_signs_are_encoded_so_nginx_cannot_decode_them_into_dots(share_root: Path):
    (share_root / "shared" / "%2e%2e").write_text("x")
    (share_root / "shared" / "a%2fb.txt").write_text("x")
    manifest = share_zip.build_manifest(_browser(share_root, ["shared"]))
    files = dict((name, location) for location, name in assert_list_invariants(manifest.body, share_root, ["shared"]))
    assert files["shared/%2e%2e"].endswith("/shared/%252e%252e")
    assert files["shared/a%2fb.txt"].endswith("/shared/a%252fb.txt")


def test_spaces_and_non_ascii_are_encoded_in_the_location_only(share_root: Path):
    (share_root / "shared" / "Ümlaut Datei.txt").write_text("x")
    manifest = share_zip.build_manifest(_browser(share_root, ["shared"]))
    files = dict((name, location) for location, name in assert_list_invariants(manifest.body, share_root, ["shared"]))
    assert files["shared/Ümlaut Datei.txt"].endswith("/shared/%C3%9Cmlaut%20Datei.txt")


def test_retargeted_symlink_is_rechecked_without_the_cache(share_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The walk and file lookups are cached for a minute in prod. A link that was inside the share when they
    were cached and points outside now must not reach nginx, which would follow it."""
    (tmp_path / "secret.txt").write_text("secret")
    link = share_root / "shared" / "link.txt"
    link.symlink_to("report.txt")
    browser = _browser(share_root, ["shared"])
    cached_walk = list(browser.walk_contents(Path("shared")))
    assert (Path("shared/link.txt"), False) in cached_walk  # control: listed while it points inside

    link.unlink()
    link.symlink_to(tmp_path / "secret.txt")
    monkeypatch.setattr(browser, "walk_contents", lambda subpath: iter(cached_walk))
    monkeypatch.setattr(browser, "get_file", lambda subpath: browser.root_dir / subpath)  # a stale cache hit

    manifest = share_zip.build_manifest(browser)
    assert "link.txt" not in manifest.body
    assert_list_invariants(manifest.body, share_root, ["shared"])


def test_symlinks_inside_the_root_behave_like_single_downloads(share_root: Path):
    """docs/file-share.md#symlinks: a file link inside a shared folder serves its target from anywhere in the
    share root; the files of a folder link pointing outside the token's paths are listed but not served."""
    shared = share_root / "shared"
    (shared / "file-link.txt").symlink_to("../unshared.txt")
    (shared / "folder-link").symlink_to("../other", target_is_directory=True)
    (shared / "inner-link").symlink_to("nested", target_is_directory=True)
    browser = _browser(share_root, ["shared"])
    names = _names(share_zip.build_manifest(browser))

    assert "shared/file-link.txt" in names
    assert "shared/folder-link/other.txt" not in names
    assert ("shared/folder-link/other.txt" in names) == (browser.get_file(Path("shared/folder-link/other.txt")) is not None)
    assert "shared/inner-link/child.txt" in names  # a folder link inside the share is followed, like WebDAV
    assert_list_invariants(share_zip.build_manifest(browser).body, share_root, ["shared"])


def test_hidden_and_junk_files_are_left_out(share_root: Path):
    shared = share_root / "shared"
    (shared / ".ngsignore").write_text("*.tmp\nignored-dir/\n")
    (shared / "scratch.tmp").write_text("x")
    (shared / "ignored-dir").mkdir()
    (shared / "ignored-dir" / "keep.txt").write_text("x")
    (shared / "nested" / ".ngsignore").write_text("!scratch.tmp\nsecret.txt\n")
    (shared / "nested" / "secret.txt").write_text("x")
    (shared / "nested" / "scratch.tmp").write_text("x")  # re-included below
    (shared / "ignored-dir" / ".ngsignore").write_text("!keep.txt\n")  # can't re-include below an ignored folder
    (share_root / ".ngsignore").write_text("report.txt\n")

    names = _names(share_zip.build_manifest(_browser(share_root, ["shared"])))
    for hidden in ("report.txt", "scratch.tmp", "ignored-dir", "secret.txt", ".ngsignore", ".DS_Store", "._report.txt"):
        assert not any(name.endswith(hidden) or f"/{hidden}/" in name for name in names if name != "shared/nested/scratch.tmp"), hidden
    assert "shared/nested/scratch.tmp" in names
    assert "shared/nested/child.txt" in names


def test_shared_paths_with_the_same_name_get_numbered(share_root: Path):
    for parent in ("a", "b"):
        (share_root / parent / "data").mkdir(parents=True)
        (share_root / parent / "data" / f"{parent}.txt").write_text(parent)
    manifest = share_zip.build_manifest(_browser(share_root, ["a/data", "b/data"]))
    assert _names(manifest) == ["data (2)/b.txt", "data/a.txt"]
    assert manifest.n_files == 2 and manifest.total_size == 2


def test_nothing_to_download(share_root: Path):
    (share_root / "only-empty").mkdir()
    assert share_zip.build_manifest(_browser(share_root, ["only-empty"])) is None
    assert share_zip.build_manifest(_browser(share_root, ["missing"])) is None


@pytest.mark.parametrize("subpath", ["../share", "shared/../other", "shared/nested/../../other", "/etc", "."])
def test_traversal_in_a_folder_path_is_refused(share_root: Path, subpath: str):
    assert share_zip.build_manifest(_browser(share_root, ["shared"]), Path(subpath)) is None


@pytest.mark.parametrize("subpath", ["shared/../other", "shared/nested/../../other", "/etc"])
def test_traversal_guards_hold_without_the_safety_check(share_root: Path, monkeypatch: pytest.MonkeyPatch, subpath: str):
    """`is_safe` refuses these too; the zip's own guards must hold on their own if it ever regresses."""
    browser = _browser(share_root, ["shared"])
    monkeypatch.setattr(browser, "is_safe", lambda _subpath: True)
    assert share_zip._has_traversal(Path(subpath))  # the walk refuses them too, so the result alone can't tell
    assert share_zip.build_manifest(browser, Path(subpath)) is None
    assert list(browser.walk_contents(Path(subpath))) == []


@pytest.mark.parametrize("body", [
    pytest.param("- 4 /nginx-media/x.txt x.txt\n", id="other-internal-location"),
    pytest.param("- 4 /nginx-share/../etc/passwd passwd\n", id="dotdot-location"),
    pytest.param("- 4 /nginx-share/%2e%2e/etc/passwd passwd\n", id="encoded-dotdot-location"),
    pytest.param("- 4 /nginx-share/a.txt ../a.txt\n", id="dotdot-name"),
    pytest.param("- 4 /nginx-share/a.txt /etc/a.txt\n", id="absolute-name"),
    pytest.param("- 4 /nginx-share/a.txt a\\..\\b.txt\n", id="backslash-name"),
    pytest.param("- 4 /nginx-share/a.txt C:a.txt\n", id="drive-name"),
    pytest.param("deadbeef 4 /nginx-share/a.txt a.txt\n", id="unexpected-crc"),
    pytest.param("0 0 @directory a\n", id="directory-without-slash"),
    pytest.param("- 4 /nginx-share/a.txt\n", id="missing-name"),
    pytest.param("- x /nginx-share/a.txt a.txt\n", id="bad-size"),
])
def test_validate_body_rejects_unsafe_lines(body: str):
    with pytest.raises(ValueError):
        share_zip.validate_body(body)


def test_validate_body_accepts_a_good_list():
    share_zip.validate_body("0 0 @directory a/\n- 4 /nginx-share//a/b%20c.txt a/b c.txt\n")


# ── nginx config ────────────────────────────────────────────────────────────


# mounted by compose.test.yaml
NGINX_DIR = Path("/app/services/nginx")


@pytest.mark.parametrize("conf", ["nginx.template.conf", "nginx.dev.conf.template"])
def test_nginx_config_keeps_share_files_internal(conf: str):
    text = (NGINX_DIR / conf).read_text()
    share = re.search(r"location /nginx-share/ \{(.*?)\}", text, re.S)
    assert share and "internal;" in share.group(1)
    zip_location = re.search(r"location /api/shares/zip/ \{(.*?)\}", text, re.S)
    assert zip_location, "the zip location (longer proxy timeout) is missing"
    assert "proxy_set_header X-Archive-Support zip;" in zip_location.group(1)
    assert not re.search(r"^\s*(alias|root)\s", zip_location.group(1), re.M), "the zip location must only proxy"
    app = re.search(r"location / \{(.*?)\}", text, re.S)
    assert app and "proxy_set_header X-Archive-Support zip;" in app.group(1)
