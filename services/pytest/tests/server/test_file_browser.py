from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.core import config

from ._http import get


def test_file_browser_renders_list_and_lazy_directory_fragments(
    client: TestClient,
    insider_token: str,
    tmp_path: Path,
):
    share_root = tmp_path / "share"
    nested = share_root / "nested"
    nested.mkdir(parents=True)
    (share_root / "root.txt").write_text("root")
    (nested / "child.txt").write_text("child")

    original_share_root = config.settings.app_config.share_root
    config.settings.app_config.share_root = str(share_root)
    try:
        page = get(client, "/browser/", insider_token)
        assert page.status_code == 200
        assert 'id="file-browser-root"' in page.text
        assert "hx-trigger=\"load\"" in page.text
        assert "<table" not in page.text
        # selection panel for Associate/Share, hidden until something is selected
        assert 'id="path-selection-panel"' in page.text
        assert 'data-max-paths="50"' in page.text
        assert "js/path-selection.js" in page.text

        root = get(client, "/htmx/files/", insider_token)
        assert root.status_code == 200
        assert "nested/" in root.text
        assert 'hx-trigger="click once"' in root.text
        assert "browser-children" in root.text

        children = get(client, "/htmx/files/nested", insider_token)
        assert children.status_code == 200
        assert "child.txt" in children.text
    finally:
        config.settings.app_config.share_root = original_share_root


@pytest.fixture
def share_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "share"
    report = root / "proj" / "report"
    (report / "img").mkdir(parents=True)
    (report / "multiqc_report.html").write_text('<img src="img/plot.png">')
    (report / "img" / "plot.png").write_bytes(b"png")
    (report / "samples.tsv").write_text("a\tb\n")
    (report / "summary.pdf").write_bytes(b"pdf")
    (report / "sample.bam").write_bytes(b"bam")
    (report / "disguised.html").symlink_to(report / "sample.bam")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.pdf").write_bytes(b"leak")
    (report / "escape").symlink_to(outside, target_is_directory=True)

    original_share_root = config.settings.app_config.share_root
    config.settings.app_config.share_root = str(root)
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "test")
    try:
        yield root
    finally:
        config.settings.app_config.share_root = original_share_root


def test_file_browser_links_viewable_files(client: TestClient, insider_token: str, share_root: Path):
    listing = get(client, "/htmx/files/proj/report", insider_token)
    assert listing.status_code == 200
    for name in ("multiqc_report.html", "samples.tsv", "summary.pdf"):
        assert f'/htmx/share-files/proj/report/{name}"' in listing.text
    assert "sample.bam" in listing.text
    assert "/htmx/share-files/proj/report/sample.bam" not in listing.text
    # unlike the Data tabs, the insider browser doesn't grey out what it can't open
    assert "browser-entry-unavailable" not in listing.text

    # the picker only selects
    picker = get(client, "/htmx/files/proj/report?pick=1", insider_token)
    assert "/htmx/share-files/" not in picker.text


@pytest.mark.parametrize("subpath, content, disposition", [
    ("proj/report/multiqc_report.html", b'<img src="img/plot.png">', "inline"),
    ("proj/report/img/plot.png", b"png", "inline"),
    ("proj/report/samples.tsv", b"a\tb\n", "inline"),
    ("proj/report/summary.pdf", b"pdf", "inline"),
])
def test_file_browser_serves_viewable_files(
    client: TestClient, insider_token: str, share_root: Path, subpath: str, content: bytes, disposition: str,
):
    response = get(client, f"/htmx/share-files/{subpath}", insider_token)
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-disposition"].startswith(disposition)


@pytest.mark.parametrize("subpath, status", [
    ("proj/report/sample.bam", 403),
    ("proj/report/disguised.html", 403),  # symlink to the bam
    ("proj/report/escape/leak.pdf", 404),
    ("proj/report/..%2F..%2F..%2Foutside/leak.pdf", 404),
    ("proj/report/nope.pdf", 404),
    ("proj/report", 404),
])
def test_file_browser_refuses_other_files(
    client: TestClient, insider_token: str, share_root: Path, subpath: str, status: int,
):
    assert get(client, f"/htmx/share-files/{subpath}", insider_token).status_code == status


def test_file_browser_files_are_for_insiders(client: TestClient, user_token: str, share_root: Path):
    assert get(client, "/htmx/share-files/proj/report/summary.pdf", user_token).status_code in (401, 403)
    assert get(client, "/htmx/share-files/proj/report/summary.pdf").status_code in (303, 401)


def test_file_browser_serves_through_nginx_in_prod(
    client: TestClient, insider_token: str, share_root: Path, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "prod")
    response = get(client, "/htmx/share-files/proj/report/summary.pdf", insider_token)
    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["x-accel-redirect"].startswith("/nginx-share/")
