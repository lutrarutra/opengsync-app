"""Project Data tab: a file browser limited to the project's data paths, serving only viewable file types."""

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from opengsync_db import SyncSession, models, queries as Q, categories as C
from redis import Redis

from server.core import config
from server.utils.shared_file_browser import SharedFileBrowser

from ._http import get

REPORT_HTML = '<html><body><img src="img/plot.png"></body></html>'


@dataclass(frozen=True)
class ProjectData:
    project: models.Project
    root: Path


@pytest.fixture
def project_data(
    session: SyncSession,
    user: models.User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    share_root = tmp_path / "share"
    report = share_root / "proj" / "report"
    (report / "img").mkdir(parents=True)
    (report / "multiqc_report.html").write_text(REPORT_HTML)
    (report / "img" / "plot.png").write_bytes(b"png")
    (report / "my plot.png").write_bytes(b"spaced")
    (report / "summary.PDF").write_bytes(b"pdf")
    (report / "sample.bam").write_bytes(b"bam")
    (report / "reads.fastq.gz").write_bytes(b"fastq")
    (report / "disguised.html").symlink_to(report / "sample.bam")
    (share_root / "other").mkdir()
    (share_root / "other" / "private.pdf").write_bytes(b"private")
    (share_root / "single.pdf").write_bytes(b"single")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.pdf").write_bytes(b"leak")
    (report / "escape").symlink_to(outside, target_is_directory=True)

    original_share_root = config.settings.app_config.share_root
    config.settings.app_config.share_root = str(share_root)
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "test")
    try:
        project = session.save(Q.project.create(title="data", description="d", owner_id=user.id), flush=True)
        for path, type in [
            ("proj/report", C.DataPathType.DIRECTORY),
            ("proj/report/img", C.DataPathType.DIRECTORY),  # nested in proj/report, not listed separately
            ("single.pdf", C.DataPathType.PDF),
            ("missing/dir", C.DataPathType.DIRECTORY),  # gone from disk
        ]:
            session.save(Q.data_path.create(path=path, type=type, project=project), flush=True)
        session.commit()
        yield ProjectData(project=project, root=share_root)
    finally:
        config.settings.app_config.share_root = original_share_root


def _browse(project: models.Project, subpath: str = "") -> str:
    return f"/htmx/projects/{project.id}/browse" + (f"/{subpath}" if subpath else "")


def _file(project: models.Project, subpath: str) -> str:
    return f"/htmx/projects/{project.id}/files/{subpath}"


def _without_entry_ids(html: str) -> str:
    """Directory entries get a fresh uuid per render."""
    return re.sub(r"browser-children-[0-9a-f-]+", "browser-children-", html)


def test_project_page_embeds_browser(client: TestClient, project_data: ProjectData, user_token: str):
    page = get(client, f"/projects/{project_data.project.id}", user_token)
    assert page.status_code == 200
    assert 'id="file-browser-root"' in page.text
    assert _browse(project_data.project) in page.text
    assert "render-data_path-table-page" not in page.text


def test_root_lists_top_level_data_paths(
    client: TestClient, project_data: ProjectData, user_token: str,
):
    root = get(client, _browse(project_data.project), user_token)
    assert root.status_code == 200
    assert "proj/report/" in root.text
    assert "single.pdf" in root.text
    assert "proj/report/img/" not in root.text
    assert "other" not in root.text
    assert "Remove from project" not in root.text

    # a data path missing from storage is still listed, marked and without a link
    assert "missing/dir" in root.text
    assert "not found on storage" in root.text
    assert _browse(project_data.project, "missing/dir") not in root.text
    assert _file(project_data.project, "missing/dir") not in root.text
    assert "No data has been added" not in root.text


def test_root_with_all_data_paths_missing_still_lists_them(
    client: TestClient, session: SyncSession, user: models.User, user_token: str, tmp_path: Path,
):
    original_share_root = config.settings.app_config.share_root
    config.settings.app_config.share_root = str(tmp_path / "empty-share")
    try:
        project = session.save(Q.project.create(title="unmounted", description="d", owner_id=user.id), flush=True)
        for path in ("BSF_SAMPLES/a", "BSF_SAMPLES/b"):
            session.save(Q.data_path.create(path=path, type=C.DataPathType.DIRECTORY, project=project), flush=True)
        session.commit()

        root = get(client, _browse(project), user_token)
        assert root.status_code == 200
        assert "BSF_SAMPLES/a" in root.text
        assert "BSF_SAMPLES/b" in root.text
        assert root.text.count('class="browser-entry-missing"') == 2
        assert "No data has been added" not in root.text
    finally:
        config.settings.app_config.share_root = original_share_root


def _order(html: str, *names: str) -> list[str]:
    """`names` in the order the listing shows them."""
    return sorted(names, key=lambda name: html.index(f'title="{name}'))


def test_names_collapse_in_the_middle(client: TestClient, project_data: ProjectData, user_token: str):
    root = get(client, _browse(project_data.project), user_token)
    # a top-level path keeps its last component visible, directories get the slash on that side
    assert '<span class="begin">proj/</span><span class="end">report/</span>' in root.text
    assert '<span class="begin">missing/</span><span class="end">dir</span>' in root.text

    listing = get(client, _browse(project_data.project, "proj/report"), user_token)
    # a plain name keeps its second half (at most 16 characters), so the extension stays visible
    assert '<span class="begin">multiqc_re</span><span class="end">port.html</span>' in listing.text
    assert 'title="sample.bam (not viewable in the browser' in listing.text


def test_toolbar_sorts_client_side(client: TestClient, project_data: ProjectData, user_token: str):
    page = get(client, f"/projects/{project_data.project.id}", user_token)
    assert f'data-entries-url="http://testserver{_browse(project_data.project)}"' in page.text
    assert 'data-sort-by="name"' in page.text
    assert 'data-sort-order="asc"' in page.text
    assert page.text.count('onclick="sortFileBrowser(this)"') == 3
    assert "bi-arrow-up" in page.text


@pytest.mark.parametrize("sort_order, expected", [
    ("asc", ["proj/report", "single.pdf", "missing/dir"]),
    ("desc", ["single.pdf", "proj/report", "missing/dir"]),
])
def test_root_sorts_by_name_in_both_directions(
    client: TestClient, project_data: ProjectData, user_token: str, sort_order: str, expected: list[str],
):
    root = get(client, _browse(project_data.project), user_token, params={"sort_by": "name", "sort_order": sort_order})
    assert root.status_code == 200
    assert _order(root.text, *expected) == expected


def test_all_missing_roots_follow_name_direction(
    client: TestClient, session: SyncSession, user: models.User, user_token: str, tmp_path: Path,
):
    original_share_root = config.settings.app_config.share_root
    config.settings.app_config.share_root = str(tmp_path / "empty-share")
    try:
        project = session.save(Q.project.create(title="unmounted", description="d", owner_id=user.id), flush=True)
        for path in ("a/one", "b/two"):
            session.save(Q.data_path.create(path=path, type=C.DataPathType.DIRECTORY, project=project), flush=True)
        session.commit()

        ascending = get(client, _browse(project), user_token, params={"sort_by": "name", "sort_order": "asc"})
        descending = get(client, _browse(project), user_token, params={"sort_by": "name", "sort_order": "desc"})
        assert _order(ascending.text, "a/one", "b/two") == ["a/one", "b/two"]
        assert _order(descending.text, "a/one", "b/two") == ["b/two", "a/one"]
    finally:
        config.settings.app_config.share_root = original_share_root


@pytest.mark.parametrize("sort_by, sort_order, expected", [
    ("size", "desc", ["multiqc_report.html", "my plot.png", "sample.bam"]),
    ("size", "asc", ["sample.bam", "my plot.png", "multiqc_report.html"]),
    ("name", "asc", ["multiqc_report.html", "my plot.png", "sample.bam"]),
    ("name", "desc", ["sample.bam", "my plot.png", "multiqc_report.html"]),
])
def test_directory_sorts_in_both_directions(
    client: TestClient, project_data: ProjectData, user_token: str, sort_by: str, sort_order: str, expected: list[str],
):
    listing = get(
        client, _browse(project_data.project, "proj/report"), user_token,
        params={"sort_by": sort_by, "sort_order": sort_order},
    )
    assert listing.status_code == 200
    assert _order(listing.text, *expected) == expected
    # directories expanded from this listing load with the same sort
    assert f"sort_by={sort_by}&amp;sort_order={sort_order}" in listing.text or f"sort_by={sort_by}&sort_order={sort_order}" in listing.text


def test_root_offers_removal_to_insiders(client: TestClient, project_data: ProjectData, insider_token: str):
    root = get(client, _browse(project_data.project), insider_token)
    assert root.status_code == 200
    assert "Remove from project" in root.text
    assert "cm-callback" in root.text


def test_listing_links_only_servable_files(client: TestClient, project_data: ProjectData, user_token: str):
    listing = get(client, _browse(project_data.project, "proj/report"), user_token)
    assert listing.status_code == 200
    project = project_data.project

    # url_for renders absolute URLs, so match the path and the closing quote
    assert f'{_file(project, "proj/report/multiqc_report.html")}"' in listing.text
    assert f'{_file(project, "proj/report/summary.PDF")}"' in listing.text
    assert "sample.bam" in listing.text
    assert "reads.fastq.gz" in listing.text
    assert _file(project, "proj/report/sample.bam") not in listing.text
    assert _file(project, "proj/report/reads.fastq.gz") not in listing.text
    assert "browser-entry-unavailable" in listing.text
    assert "img/" in listing.text


def test_file_names_are_url_encoded_once(client: TestClient, project_data: ProjectData, user_token: str):
    listing = get(client, _browse(project_data.project, "proj/report"), user_token)
    assert _file(project_data.project, "proj/report/my%20plot.png") in listing.text
    assert "%2520" not in listing.text

    served = get(client, _file(project_data.project, "proj/report/my%20plot.png"), user_token)
    assert served.status_code == 200
    assert served.content == b"spaced"


def test_serves_report_and_its_relative_assets(client: TestClient, project_data: ProjectData, user_token: str):
    project = project_data.project
    report = get(client, _file(project, "proj/report/multiqc_report.html"), user_token)
    assert report.status_code == 200
    assert report.text == REPORT_HTML
    assert report.headers["content-disposition"].startswith("inline")

    # what the browser requests for <img src="img/plot.png"> on that page
    asset = get(client, _file(project, "proj/report/img/plot.png"), user_token)
    assert asset.status_code == 200
    assert asset.content == b"png"

    single = get(client, _file(project, "single.pdf"), user_token)
    assert single.status_code == 200
    assert single.content == b"single"

    upper_case = get(client, _file(project, "proj/report/summary.PDF"), user_token)
    assert upper_case.status_code == 200


@pytest.mark.parametrize("subpath", [
    "proj/report/sample.bam",
    "proj/report/reads.fastq.gz",
    "proj/report/disguised.html",  # symlink to the bam
])
def test_refuses_data_files(client: TestClient, project_data: ProjectData, user_token: str, subpath: str):
    assert get(client, _file(project_data.project, subpath), user_token).status_code == 403


@pytest.mark.parametrize("subpath", [
    "other/private.pdf",
    "proj/report/..%2F..%2Fother/private.pdf",
    "proj/report/escape/leak.pdf",
    "proj/report/nope.pdf",
])
def test_refuses_paths_outside_data_paths(
    client: TestClient, project_data: ProjectData, user_token: str, subpath: str,
):
    assert get(client, _file(project_data.project, subpath), user_token).status_code == 404


def test_listing_outside_data_paths_is_empty(client: TestClient, project_data: ProjectData, user_token: str):
    listing = get(client, _browse(project_data.project, "other"), user_token)
    assert listing.status_code == 200
    assert "private.pdf" not in listing.text

    escaped = get(client, _browse(project_data.project, "proj/report/escape"), user_token)
    assert escaped.status_code == 200
    assert "leak.pdf" not in escaped.text


def test_requires_project_read_access(
    client: TestClient, project_data: ProjectData, user_2_token: str, insider_token: str,
):
    project = project_data.project
    assert get(client, _browse(project), user_2_token).status_code == 403
    assert get(client, _browse(project, "proj/report"), user_2_token).status_code == 403
    assert get(client, _file(project, "proj/report/multiqc_report.html"), user_2_token).status_code == 403

    assert get(client, _browse(project), insider_token).status_code == 200
    assert get(client, _file(project, "proj/report/multiqc_report.html"), insider_token).status_code == 200

    anonymous = get(client, _file(project, "proj/report/multiqc_report.html"))
    assert anonymous.status_code in (303, 401)


def test_prod_serves_files_through_nginx(
    client: TestClient, project_data: ProjectData, user_token: str, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "prod")
    response = get(client, _file(project_data.project, "proj/report/multiqc_report.html"), user_token)
    assert response.status_code == 200
    assert response.content == b""
    accel = response.headers["x-accel-redirect"]
    assert accel.startswith("/nginx-share/")
    assert accel.endswith("proj/report/multiqc_report.html")


def test_prod_refuses_to_serve_from_the_app(
    client: TestClient, project_data: ProjectData, user_token: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    # the browser resolves the symlinked root, so the file no longer maps onto the configured share root
    link = tmp_path / "share-link"
    link.symlink_to(project_data.root, target_is_directory=True)
    config.settings.app_config.share_root = str(link)
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "prod")

    lenient = TestClient(client.app, raise_server_exceptions=False)
    response = get(lenient, _file(project_data.project, "proj/report/multiqc_report.html"), user_token)
    assert response.status_code == 500
    assert REPORT_HTML not in response.text


def test_prod_caches_lookups_and_listings(
    client: TestClient,
    session: SyncSession,
    project_data: ProjectData,
    user_token: str,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "prod")
    redis = Redis(connection_pool=client.app.state.redis_pool)
    project = project_data.project

    assert get(client, _file(project, "proj/report/img/plot.png"), user_token).status_code == 200
    assert get(client, _file(project, "proj/report/new.pdf"), user_token).status_code == 404
    first_listing = get(client, _browse(project, "proj/report"), user_token)
    first_root = get(client, _browse(project), user_token)
    assert list(redis.scan_iter(match=f"share-fs:project:{project.id}:*:file:*"))

    def no_filesystem_checks(*args, **kwargs):
        raise AssertionError("safety check ran on a cache hit")

    monkeypatch.setattr(SharedFileBrowser, "is_safe", no_filesystem_checks)
    monkeypatch.setattr(SharedFileBrowser, "_is_safe", no_filesystem_checks)

    assert get(client, _file(project, "proj/report/img/plot.png"), user_token).status_code == 200
    listing = get(client, _browse(project, "proj/report"), user_token)
    assert _without_entry_ids(listing.text) == _without_entry_ids(first_listing.text)
    root = get(client, _browse(project), user_token)
    assert _without_entry_ids(root.text) == _without_entry_ids(first_root.text)

    # misses are cached as well
    (project_data.root / "proj" / "report" / "new.pdf").write_bytes(b"new")
    assert get(client, _file(project, "proj/report/new.pdf"), user_token).status_code == 404
    monkeypatch.undo()
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "prod")

    # a file deleted after its lookup was cached is re-checked when served
    (project_data.root / "proj" / "report" / "img" / "plot.png").unlink()
    assert get(client, _file(project, "proj/report/img/plot.png"), user_token).status_code == 404

    # a new data path changes the cache key, so it shows up without waiting for the TTL
    session.save(Q.data_path.create(path="other", type=C.DataPathType.DIRECTORY, project=project), flush=True)
    session.commit()
    root = get(client, _browse(project), user_token)
    assert "other/" in root.text
    assert get(client, _file(project, "other/private.pdf"), user_token).status_code == 200


def test_admin_browser_directories_have_context_menu(
    client: TestClient, project_data: ProjectData, insider_token: str,
):
    root = get(client, "/htmx/files/", insider_token)
    assert root.status_code == 200
    assert "cm-callback" in root.text
    assert "Share Directory" in root.text
