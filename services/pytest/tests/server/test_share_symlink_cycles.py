"""Symlink cycles inside a shared folder: listings and downloads must work, and a recursive client must end.

Links that leave the share root are covered in test_share_root_abuse.py; the fs-index side of both
cases in tests/worker/test_fs_index.py.

    share/                      <- share_root
      shared/                   <- the only path the share link exposes
        report.txt
        sub/data.txt
        sub/up    -> ..         its own parent
        self      -> .          its own folder
        loop_a    -> loop_b     point at each other: ELOOP
        loop_b    -> loop_a
        dangling  -> missing
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q

from server.core import config
from server.utils import share_zip
from server.utils.shared_file_browser import SharedFileBrowser

# far deeper than the layout: reaching it means the walk went round a cycle
MAX_DEPTH = 12


@pytest.fixture
def share_root(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Requests `client` so the app config exists before share_root is patched."""
    root = tmp_path / "share"
    shared = root / "shared"
    (shared / "sub").mkdir(parents=True)
    (shared / "report.txt").write_text("report")
    (shared / "sub" / "data.txt").write_text("data")
    (shared / "sub" / "up").symlink_to("..", target_is_directory=True)
    (shared / "self").symlink_to(".", target_is_directory=True)
    (shared / "loop_a").symlink_to("loop_b")
    (shared / "loop_b").symlink_to("loop_a")
    (shared / "dangling").symlink_to("missing")
    monkeypatch.setattr(config.settings.app_config, "share_root", str(root))
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "test")
    return root


@pytest.fixture
def share_link(session: SyncSession, user: models.User, share_root: Path) -> str:
    token = session.save(Q.share_token.create(owner=user, time_valid_min=60, paths=["shared"]), flush=True)
    session.commit()
    return token.uuid


LIST_ROUTES = [
    pytest.param("GET", "/api/shares/browse/{token}/{path}", id="browse"),
    pytest.param("GET", "/api/shares/rclone/{token}/{path}", id="rclone"),
    pytest.param("GET", "/files/share/browse/{token}/entries/{path}", id="entries"),
    pytest.param("PROPFIND", "/api/webdav/{token}/{path}", id="webdav-propfind"),
    pytest.param("GET", "/api/shares/zip/{token}/{path}", id="zip"),
]
FILE_ROUTES = [
    pytest.param("GET", "/api/shares/browse/{token}/{path}", id="browse"),
    pytest.param("GET", "/api/shares/rclone/{token}/{path}", id="rclone"),
    pytest.param("GET", "/api/webdav/{token}/{path}", id="webdav-get"),
]


def _request(client: TestClient, method: str, route: str, token: str, path: str):
    # X-Archive-Support: set by nginx when it can stream zips; the zip route refuses requests without it
    return client.request(method, route.format(token=token, path=path), headers={"Depth": "1", "X-Archive-Support": "zip"})


# ── loops and dangling links: skipped, never an error ───────────────────────


@pytest.mark.parametrize("method,route", LIST_ROUTES)
def test_listing_skips_looping_and_dangling_symlinks(
    client: TestClient, share_link: str, method: str, route: str,
):
    response = _request(client, method, route, share_link, "shared")
    assert response.status_code in (200, 207), response.text[:500]
    assert "report.txt" in response.text  # control: the listing is the real one
    for name in ("loop_a", "loop_b", "dangling"):
        assert name not in response.text


@pytest.mark.parametrize("method,route", FILE_ROUTES)
@pytest.mark.parametrize("name", ["loop_a", "dangling"])
def test_looping_and_dangling_symlinks_are_not_served(
    client: TestClient, share_link: str, method: str, route: str, name: str,
):
    response = _request(client, method, route, share_link, f"shared/{name}")
    assert 400 <= response.status_code < 500, response.status_code
    assert "content-disposition" not in response.headers


@pytest.mark.parametrize("method,route", FILE_ROUTES)
def test_file_route_control(client: TestClient, share_link: str, method: str, route: str):
    """The file routes do serve a shared file, so the rejections above are meaningful."""
    response = _request(client, method, route, share_link, "shared/sub/data.txt")
    assert response.status_code == 200, response.text[:500]
    assert response.text == "data"


# ── cycles: a recursive client must end ─────────────────────────────────────


def _walk(browser: SharedFileBrowser, subpath: Path, depth: int = 0) -> list[Path]:
    """Every file a recursive client downloads, as share-relative paths; folders are entered as listed."""
    assert depth < MAX_DEPTH, f"still descending at {subpath}: the walk follows a symlink cycle"
    files = []
    for entry in browser.list_contents(subpath):
        if entry.is_dir:
            files += _walk(browser, entry.rel_path, depth + 1)
        else:
            files.append(entry.rel_path)
    return files


def test_walk_without_cycles_is_the_control(share_root: Path):
    (share_root / "shared" / "self").unlink()
    (share_root / "shared" / "sub" / "up").unlink()
    browser = SharedFileBrowser(share_root, ["shared"], cache_key="cycles-control")
    assert sorted(p.as_posix() for p in _walk(browser, Path("shared"))) == ["shared/report.txt", "shared/sub/data.txt"]


def test_recursive_walk_ends_and_reaches_each_file_once(share_root: Path):
    browser = SharedFileBrowser(share_root, ["shared"], cache_key="cycles")
    files = _walk(browser, Path("shared"))
    resolved = [(share_root / p).resolve() for p in files]
    assert sorted(set(resolved)) == sorted([
        (share_root / "shared" / "report.txt").resolve(),
        (share_root / "shared" / "sub" / "data.txt").resolve(),
    ])
    assert len(resolved) == len(set(resolved)), f"files reached more than once: {sorted(map(str, files))}"


@pytest.mark.parametrize("method,route", LIST_ROUTES)
@pytest.mark.parametrize("path", ["shared/self/self/sub", "shared/sub/up/sub/up/sub"])
def test_listing_through_a_cycle_is_refused(
    client: TestClient, share_link: str, method: str, route: str, path: str,
):
    response = _request(client, method, route, share_link, path)
    assert "data.txt" not in response.text


@pytest.mark.parametrize("method,route", FILE_ROUTES)
@pytest.mark.parametrize("path", ["shared/self/self/report.txt", "shared/sub/up/sub/up/sub/data.txt"])
def test_file_through_a_cycle_is_not_served(
    client: TestClient, share_link: str, method: str, route: str, path: str,
):
    response = _request(client, method, route, share_link, path)
    assert response.status_code >= 400, response.status_code


# ── zip downloads: the walk behind the file list must end too ───────────────


def _zip_names(browser: SharedFileBrowser, subpath: Path | None = None) -> list[str]:
    manifest = share_zip.build_manifest(browser, subpath)
    assert manifest is not None
    return [line.split(" ", 3)[3] for line in manifest.body.splitlines()]


def test_zip_list_ends_and_lists_each_file_once(share_root: Path):
    names = _zip_names(SharedFileBrowser(share_root, ["shared"], cache_key="zip-cycles"))
    assert names == ["shared/report.txt", "shared/sub/", "shared/sub/data.txt"]


def test_zip_list_ends_on_folders_linking_to_each_other(share_root: Path):
    """a/to_b -> b and b/to_a -> a: no link points at its own ancestor, so only the walk's own guard
    (the real paths of the folders above) stops it."""
    shared = share_root / "shared"
    for name in ("a", "b"):
        (shared / name).mkdir()
        (shared / name / f"{name}.txt").write_text(name)
    (shared / "a" / "to_b").symlink_to("../b", target_is_directory=True)
    (shared / "b" / "to_a").symlink_to("../a", target_is_directory=True)

    names = _zip_names(SharedFileBrowser(share_root, ["shared"], cache_key="zip-mutual"))
    assert max(name.count("/") for name in names) < MAX_DEPTH
    # each folder is entered once through the other's link, never a second time
    assert "shared/a/to_b/b.txt" in names and "shared/b/to_a/a.txt" in names
    assert not any("to_b/to_a" in name or "to_a/to_b" in name for name in names)
