"""fs-index search: insider file browser and project Data tab search, over an index built in the test.

The index is written directly (the worker's import and crawl are tested in tests/worker/test_fs_index.py);
the share tree on disk exists too, because project results are checked live.
"""
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, models, queries as Q, categories as C
from opengsync_db.fs_index import FsIndexDBHandler, connect_writer, ensure_schema

from server.core import config
from server.utils import fs_index
from server.utils.file_browser import file_icon

from ._http import get

COLUMNS = ("path", "parent_id", "name", "kind", "size", "mtime", "link_target", "target_kind", "target_size",
           "hidden", "unsafe", "searchable", "opaque", "total_size", "n_files", "max_mtime")


def _index(db_file: Path, entries: list[dict]) -> None:
    ensure_schema(str(db_file))
    conn = connect_writer(str(db_file))
    ids: dict[str, int] = {}
    try:
        for entry in sorted(entries, key=lambda e: e["path"].count("/")):
            parent = entry["path"].rpartition("/")[0]
            values = {
                "parent_id": ids.get(parent), "name": entry["path"].rsplit("/", 1)[-1], "size": None,
                "mtime": 1_700_000_000, "link_target": None, "target_kind": None, "target_size": None,
                "hidden": False, "unsafe": False, "searchable": True, "opaque": False,
                "total_size": None, "n_files": None, "max_mtime": None,
            } | entry
            cursor = conn.execute(
                f"INSERT INTO entry ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                tuple(values[c] for c in COLUMNS),
            )
            ids[entry["path"]] = cursor.lastrowid
        conn.execute("INSERT INTO meta (key, value) VALUES ('crawled_at', '1700000000')")
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('last_crawl', ?), ('imported_at:BSF_PROJECTS', '1700000000')",
            ('{"checked": 42, "changed": 3, "added": 7, "removed": 1, "errors": 0, "seconds": 1.5, "at": 1700000000}',),
        )
    finally:
        conn.close()


ENTRIES = [
    {"path": "BSF_PROJECTS", "kind": "d", "total_size": 0, "n_files": 0},
    {"path": "BSF_PROJECTS/P1_Smith", "kind": "d", "total_size": 300, "n_files": 3},
    {"path": "BSF_PROJECTS/P1_Smith/counts_matrix.h5ad", "kind": "f", "size": 100},
    {"path": "BSF_PROJECTS/P1_Smith/old_matrix", "kind": "d", "total_size": 100, "n_files": 1, "mtime": 1_600_000_000},
    {"path": "BSF_PROJECTS/P1_Smith/old_matrix/x.txt", "kind": "f", "size": 100, "hidden": True},
    {"path": "BSF_PROJECTS/P1_Smith/matrix_link", "kind": "l", "link_target": None, "unsafe": True},
    {"path": "BSF_PROJECTS/P1_Smith/SC_RNA_COUNTER_CS", "kind": "d", "searchable": False, "opaque": True},
    {"path": "BSF_PROJECTS/P2_Other", "kind": "d", "total_size": 0, "n_files": 0},
    {"path": "BSF_PROJECTS/P2_Other/other_matrix.tsv", "kind": "f", "size": 5},
]


@pytest.fixture
def share_root(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "share"
    for entry in ENTRIES:
        path = root / entry["path"]
        if entry["kind"] == "d":
            path.mkdir(parents=True, exist_ok=True)
        elif entry["kind"] == "f":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * (entry.get("size") or 0))
    monkeypatch.setattr(config.settings.app_config, "share_root", str(root))
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "test")
    return root


@pytest.fixture
def index(client: TestClient, share_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "fs_index.sqlite3"
    _index(db_file, ENTRIES)
    monkeypatch.setattr(config.settings.app_config.fs_index, "enabled", True)
    monkeypatch.setattr(config.settings.app_config.fs_index, "db_file", str(db_file))
    monkeypatch.setattr(config.settings.app_config.fs_index, "dump_dir", str(tmp_path / "dumps"))
    handler = FsIndexDBHandler(str(db_file))
    client.app.state.fs_index_db = handler
    try:
        yield db_file
    finally:
        handler.close()
        client.app.state.fs_index_db = None


def _search(client: TestClient, token: str, q: str):
    return get(client, "/htmx/files/search", token, htmx=True, params={"q": q})


def test_insider_search_finds_files_and_folders(client: TestClient, index: Path, insider_token: str):
    response = _search(client, insider_token, "matrix")
    assert response.status_code == 200, response.text[:500]
    text = response.text
    for path in ("counts_matrix.h5ad", "old_matrix", "matrix_link", "other_matrix.tsv"):
        assert path in text
    # folders come first and expand into the live browser
    assert text.index("BSF_PROJECTS/P1_Smith/old_matrix") < text.index("counts_matrix.h5ad")
    assert "/htmx/files/BSF_PROJECTS/P1_Smith/old_matrix" in text
    assert "Index updated" in text


def test_search_requires_all_words(client: TestClient, index: Path, insider_token: str):
    text = _search(client, insider_token, "matrix P2").text
    assert "other_matrix.tsv" not in text  # "P2" is a path component, not part of the name
    text = _search(client, insider_token, "other matrix").text
    assert "other_matrix.tsv" in text
    assert "counts_matrix.h5ad" not in text


def test_matches_are_highlighted_and_parents_link_to_folders(client: TestClient, index: Path, insider_token: str):
    text = _search(client, insider_token, "matrix").text
    assert "counts_<mark>matrix</mark>.h5ad" in text
    # each parent folder opens as the current location (with a path bar)
    assert "/htmx/files/BSF_PROJECTS/P1_Smith?page=0&amp;located=1" in text
    assert "Hidden from share links" not in text  # nothing hidden matches
    assert "Points outside the share" in text  # matrix_link


def test_filters_by_kind_and_root(client: TestClient, index: Path, insider_token: str):
    folders = get(client, "/htmx/files/search", insider_token, htmx=True, params={"q": "matrix", "kind": "dirs"}).text
    assert "old_matrix" in folders and "counts_matrix.h5ad" not in folders
    files = get(client, "/htmx/files/search", insider_token, htmx=True, params={"q": "matrix", "kind": "files"}).text
    assert "counts_matrix.h5ad" in files and "BSF_PROJECTS/P1_Smith/old_matrix" not in files
    nowhere = get(client, "/htmx/files/search", insider_token, htmx=True, params={"q": "matrix", "root": "BSF_SAMPLES"}).text
    assert "Nothing found" in nowhere


def test_results_are_paged(
    client: TestClient, index: Path, insider_token: str, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(fs_index, "PAGE_SIZE", 2)
    first = _search(client, insider_token, "matrix").text
    assert "2+</strong> results" in first
    assert "Show more" in first and "page=1" in first
    second = get(client, "/htmx/files/search", insider_token, htmx=True, params={"q": "matrix", "page": 1}).text
    assert "search-results-header" not in second
    assert second.count('class="search-result') >= 1


def test_located_listing_has_a_path_bar(client: TestClient, index: Path, insider_token: str):
    text = get(client, "/htmx/files/BSF_PROJECTS/P1_Smith", insider_token, htmx=True, params={"located": 1}).text
    assert 'class="browser-location"' in text
    assert 'aria-current="location">P1_Smith<' in text
    assert "counts_matrix.h5ad" in text
    plain = get(client, "/htmx/files/BSF_PROJECTS/P1_Smith", insider_token, htmx=True).text
    assert 'class="browser-location"' not in plain


def test_browser_page_opens_at_a_deep_link(client: TestClient, share_root: Path, insider_token: str):
    page = get(client, "/browser/BSF_PROJECTS/P1_Smith", insider_token).text
    assert "/htmx/files/BSF_PROJECTS/P1_Smith?located=1" in page


def test_highlight_and_icons():
    assert fs_index.highlight("Counts_Matrix.h5ad", "matrix") == [("Counts_", False), ("Matrix", True), (".h5ad", False)]
    assert fs_index.highlight("abc", "BSF/abc") == [("abc", False)]  # a path query highlights nothing
    assert file_icon("reads_R1.fastq.gz", False) == "bi-file-earmark-text"
    assert file_icon("sample.bam", False) == "bi-file-earmark-binary"
    assert file_icon("data.tar.gz", False) == "bi-file-earmark-zip"
    assert file_icon("anything", True) == "bi-folder-fill"


def test_index_ignored_entries_are_not_searchable(client: TestClient, index: Path, insider_token: str):
    assert "SC_RNA_COUNTER_CS" not in _search(client, insider_token, "COUNTER").text


def test_path_query_lists_below_a_path(client: TestClient, index: Path, insider_token: str, share_root: Path):
    text = _search(client, insider_token, f"{share_root}/BSF_PROJECTS/P2_").text
    assert "other_matrix.tsv" in text
    assert "counts_matrix.h5ad" not in text


def test_short_query_asks_for_more(client: TestClient, index: Path, insider_token: str):
    response = _search(client, insider_token, "ma")
    assert response.status_code == 200
    assert "3 or more characters" in response.text


def test_search_without_index(client: TestClient, share_root: Path, insider_token: str):
    response = _search(client, insider_token, "matrix")
    assert response.status_code == 200
    assert "isn't available yet" in response.text


def test_search_is_insider_only(client: TestClient, index: Path, user_token: str):
    assert _search(client, user_token, "matrix").status_code == 403


def test_search_route_is_not_shadowed_by_browser(client: TestClient, index: Path, insider_token: str):
    # /htmx/files/{subpath} would render an (empty) directory listing for "search"
    assert "This directory is empty" not in _search(client, insider_token, "matrix").text


def test_browser_page_shows_search_box_only_when_enabled(
    client: TestClient, share_root: Path, insider_token: str, monkeypatch: pytest.MonkeyPatch,
):
    from server.core import templates
    monkeypatch.setitem(templates.j2.env.globals, "fs_index_enabled", False)
    assert "Search files and folders" not in get(client, "/browser/", insider_token).text
    monkeypatch.setitem(templates.j2.env.globals, "fs_index_enabled", True)
    page = get(client, "/browser/", insider_token).text
    assert "Search files and folders" in page
    assert 'data-search-url="http://testserver/htmx/files/search"' in page


def test_browsing_queues_directory_for_crawler(client: TestClient, index: Path, insider_token: str):
    redis = Redis(connection_pool=client.app.state.redis_pool)
    assert get(client, "/htmx/files/BSF_PROJECTS/P1_Smith", insider_token, htmx=True).status_code == 200
    assert redis.smembers(fs_index.TOUCH_KEY) == {b"BSF_PROJECTS/P1_Smith"}


# ── project Data tab ────────────────────────────────────────────────────────


@pytest.fixture
def project(session: SyncSession, user: models.User, share_root: Path) -> models.Project:
    project = session.save(Q.project.create(title="data", description="d", owner_id=user.id), flush=True)
    session.save(Q.data_path.create(path="BSF_PROJECTS/P1_Smith", type=C.DataPathType.DIRECTORY, project=project), flush=True)
    session.commit()
    return project


def _project_search(client: TestClient, token: str, project: models.Project, q: str):
    return get(client, f"/htmx/projects/{project.id}/data-search", token, htmx=True, params={"q": q})


def test_project_search_is_limited_to_visible_data(
    client: TestClient, index: Path, project: models.Project, user_token: str,
):
    response = _project_search(client, user_token, project, "matrix")
    assert response.status_code == 200, response.text[:500]
    text = response.text
    assert "counts_matrix.h5ad" in text
    assert "old_matrix" in text
    assert "other_matrix.tsv" not in text  # not a data path of this project
    assert "matrix_link" not in text  # unsafe symlink
    assert f"/htmx/projects/{project.id}/browse/BSF_PROJECTS/P1_Smith/old_matrix" in text


def test_project_search_hides_what_the_index_missed(
    client: TestClient, index: Path, project: models.Project, user_token: str, share_root: Path,
):
    # an .ngsignore written after the index was built still hides the file
    (share_root / "BSF_PROJECTS" / "P1_Smith" / ".ngsignore").write_text("*.h5ad\n")
    text = _project_search(client, user_token, project, "matrix").text
    assert "counts_matrix.h5ad" not in text
    assert "old_matrix" in text


def test_project_search_hides_symlink_the_index_thinks_is_safe(
    client: TestClient, index: Path, project: models.Project, user_token: str, share_root: Path, tmp_path: Path,
):
    """The dump maps absolute cluster links onto the share, but inside the container this one leaves it."""
    outside = tmp_path / "outside_matrix.tsv"
    outside.write_text("secret")
    (share_root / "BSF_PROJECTS" / "P1_Smith" / "abs_matrix.tsv").symlink_to(outside)
    conn = connect_writer(str(index))
    try:
        parent_id = conn.execute("SELECT id FROM entry WHERE path = 'BSF_PROJECTS/P1_Smith'").fetchone()[0]
        values = {
            "path": "BSF_PROJECTS/P1_Smith/abs_matrix.tsv", "parent_id": parent_id, "name": "abs_matrix.tsv",
            "kind": "l", "size": 30, "mtime": 1_700_000_000, "link_target": "BSF_PROJECTS/P2_Other/other_matrix.tsv",
            "target_kind": "f", "target_size": 5, "hidden": False, "unsafe": False, "searchable": True,
            "opaque": False, "total_size": None, "n_files": None, "max_mtime": None,
        }
        conn.execute(
            f"INSERT INTO entry ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
            tuple(values[c] for c in COLUMNS),
        )
    finally:
        conn.close()

    text = _project_search(client, user_token, project, "matrix").text
    assert "counts_matrix.h5ad" in text
    assert "abs_matrix.tsv" not in text


def test_project_search_needs_project_access(
    client: TestClient, index: Path, project: models.Project, user_2_token: str,
):
    assert _project_search(client, user_2_token, project, "matrix").status_code in (403, 404)


# ── dashboard status ────────────────────────────────────────────────────────


def _status(client: TestClient, token: str):
    return get(client, "/htmx/files/index-status", token, htmx=True)


def test_status_summarizes_index_and_crawler(
    client: TestClient, index: Path, insider_token: str, tmp_path: Path,
):
    (tmp_path / "dumps").mkdir()
    (tmp_path / "dumps" / "BSF_SAMPLES.jsonl.gz").write_bytes(b"")
    Redis(connection_pool=client.app.state.redis_pool).sadd(fs_index.TOUCH_KEY, "BSF_PROJECTS/P1_Smith")

    response = _status(client, insider_token)
    assert response.status_code == 200, response.text[:500]
    text = response.text
    assert "Up to date" in text
    assert "42 checked" in text
    assert "1 from browsing" in text
    assert "<code>BSF_PROJECTS</code>" in text
    assert "Waiting for import" in text and "BSF_SAMPLES.jsonl.gz" in text


def test_status_shows_worker_running(client: TestClient, index: Path, insider_token: str):
    Redis(connection_pool=client.app.state.redis_pool).set(fs_index.LOCK_KEY, "x")
    assert "Working" in _status(client, insider_token).text


def test_status_without_index(client: TestClient, share_root: Path, insider_token: str):
    response = _status(client, insider_token)
    assert response.status_code == 200
    assert "Disabled" in response.text


def test_status_is_insider_only(client: TestClient, index: Path, user_token: str):
    assert _status(client, user_token).status_code == 403


def test_dashboard_loads_status_when_enabled(
    client: TestClient, insider_token: str, monkeypatch: pytest.MonkeyPatch,
):
    from server.core import templates
    monkeypatch.setitem(templates.j2.env.globals, "fs_index_enabled", True)
    assert "/htmx/files/index-status" in get(client, "/", insider_token).text
    monkeypatch.setitem(templates.j2.env.globals, "fs_index_enabled", False)
    assert "/htmx/files/index-status" not in get(client, "/", insider_token).text


# ── stale results: the path is gone from the share but still in the index ───


@pytest.fixture
def gone(index: Path, share_root: Path) -> str:
    shutil.rmtree(share_root / "BSF_PROJECTS" / "P1_Smith" / "old_matrix")
    return "BSF_PROJECTS/P1_Smith/old_matrix"


def test_stale_result_is_still_listed(client: TestClient, gone: str, insider_token: str):
    assert gone in _search(client, insider_token, "matrix").text


def test_expanding_a_gone_folder_says_so(client: TestClient, gone: str, insider_token: str):
    text = get(client, f"/htmx/files/{gone}", insider_token, htmx=True).text
    assert "This folder no longer exists" in text
    assert "This directory is empty" not in text
    # the crawler re-checks it, which drops it from the index
    assert gone.encode() in Redis(connection_pool=client.app.state.redis_pool).smembers(fs_index.TOUCH_KEY)

    located = get(client, f"/htmx/files/{gone}", insider_token, htmx=True, params={"located": 1}).text
    assert "This folder no longer exists" in located
    assert "moved or deleted recently" in located


def test_empty_folder_is_still_empty(client: TestClient, index: Path, share_root: Path, insider_token: str):
    (share_root / "BSF_PROJECTS" / "empty").mkdir()
    text = get(client, "/htmx/files/BSF_PROJECTS/empty", insider_token, htmx=True).text
    assert "This directory is empty" in text
    assert "no longer exists" not in text


def test_share_form_warns_about_a_gone_path(client: TestClient, gone: str, bioinformatician_token: str):
    text = get(client, "/htmx/files/share-path", bioinformatician_token, params={"path": gone}).text
    assert "Not found on the share" in text
    existing = get(client, "/htmx/files/share-path", bioinformatician_token, params={"path": "BSF_PROJECTS/P1_Smith"}).text
    assert "Not found on the share" not in existing


def test_project_browser_says_a_gone_folder_is_gone(
    client: TestClient, gone: str, project: models.Project, user_token: str,
):
    text = get(client, f"/htmx/projects/{project.id}/browse/{gone}", user_token, htmx=True).text
    assert "This folder no longer exists" in text
    # outside the project's data paths nothing is revealed
    outside = get(client, f"/htmx/projects/{project.id}/browse/BSF_PROJECTS/P2_Other/nope", user_token, htmx=True).text
    assert "no longer exists" not in outside


def test_project_file_gone_message(client: TestClient, index: Path, project: models.Project, user_token: str):
    response = get(client, f"/htmx/projects/{project.id}/files/BSF_PROJECTS/P1_Smith/gone.pdf", user_token)
    assert response.status_code == 404
    assert "moved or deleted recently" in response.text
