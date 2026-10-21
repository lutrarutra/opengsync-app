"""Data tabs of projects, requests, experiments and libraries: a file browser over their own data paths,
and "Add data" (admins and bioinformaticians), which picks paths from the whole share."""

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from opengsync_db import SyncSession, models, queries as Q, categories as C

from server.core import config

from ..db.create_units import create_experiment, create_library, create_project, create_seq_request
from ._http import delete, get, post_form


@dataclass(frozen=True)
class Owner:
    entity: str
    prefix: str
    id: int
    page: str


@pytest.fixture
def share(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "share"
    (root / "runs" / "run1" / "img").mkdir(parents=True)
    (root / "runs" / "run1" / "multiqc_report.html").write_text("<html></html>")
    (root / "runs" / "run1" / "img" / "plot.png").write_bytes(b"png")
    (root / "runs" / "run1" / "reads.fastq.gz").write_bytes(b"fastq")
    (root / "other" / "reports").mkdir(parents=True)
    (root / "other" / "private.pdf").write_bytes(b"private")
    (root / "other" / "reports" / "summary.pdf").write_bytes(b"summary")

    original = config.settings.app_config.share_root
    config.settings.app_config.share_root = str(root)
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "test")
    try:
        yield root
    finally:
        config.settings.app_config.share_root = original


@pytest.fixture(params=["project", "seq_request", "library", "experiment"])
def owner(request, session: SyncSession, user: models.User, insider: models.User, share: Path) -> Owner:
    seq_request = create_seq_request(session, user)
    if request.param == "project":
        project = create_project(session, user)
        target, owner = {"project": project}, Owner("project", "projects", project.id, "projects")
    elif request.param == "seq_request":
        target, owner = {"seq_request": seq_request}, Owner("seq_request", "seq_requests", seq_request.id, "seq_requests")
    elif request.param == "library":
        library = create_library(session, user, seq_request)
        target, owner = {"library": library}, Owner("library", "libraries", library.id, "libraries")
    else:
        experiment = create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_X_1B_XP)
        target, owner = {"experiment": experiment}, Owner("experiment", "experiments", experiment.id, "experiments")
    session.save(Q.data_path.create(path="runs/run1", type=C.DataPathType.DIRECTORY, **target), flush=True)
    session.commit()
    return owner


def _label(owner: Owner) -> str:
    return {"seq_request": "request"}.get(owner.entity, owner.entity)


def _browse(owner: Owner, subpath: str = "") -> str:
    return f"/htmx/{owner.prefix}/{owner.id}/browse" + (f"/{subpath}" if subpath else "")


def test_page_embeds_the_browser(client: TestClient, owner: Owner, insider_token: str):
    page = get(client, f"/{owner.page}/{owner.id}", insider_token)
    assert page.status_code == 200
    assert 'id="file-browser-root"' in page.text
    assert _browse(owner) in page.text
    assert "render-data_path-table-page" not in page.text


def test_browses_only_its_data_paths(client: TestClient, owner: Owner, insider_token: str):
    root = get(client, _browse(owner), insider_token)
    assert root.status_code == 200
    assert "runs/run1/" in root.text
    assert "other" not in root.text

    listing = get(client, _browse(owner, "runs/run1"), insider_token)
    assert "multiqc_report.html" in listing.text
    assert f"/htmx/{owner.prefix}/{owner.id}/files/runs/run1/multiqc_report.html" in listing.text
    # listed, but only downloadable through a share link
    assert "reads.fastq.gz" in listing.text
    assert "/files/runs/run1/reads.fastq.gz" not in listing.text

    # outside the data paths: an empty listing, like the project Data tab
    outside = get(client, _browse(owner, "other"), insider_token)
    assert outside.status_code == 200
    assert "private.pdf" not in outside.text


def test_serves_viewable_files_only(client: TestClient, owner: Owner, insider_token: str):
    files = f"/htmx/{owner.prefix}/{owner.id}/files"
    assert get(client, f"{files}/runs/run1/img/plot.png", insider_token).status_code == 200
    assert get(client, f"{files}/runs/run1/reads.fastq.gz", insider_token).status_code == 403
    assert get(client, f"{files}/other/private.pdf", insider_token).status_code == 404


def test_bioinformaticians_can_remove_a_data_path(
    client: TestClient, session: SyncSession, owner: Owner, bioinformatician_token: str,
):
    root = get(client, _browse(owner), bioinformatician_token)
    assert f"Remove from {_label(owner)}" in root.text

    data_path_id = session.get_one(Q.data_path.select(**{f"{owner.entity}_id": owner.id})).id
    response = delete(
        client, f"/htmx/{owner.prefix}/{owner.id}/remove-data_path", bioinformatician_token, htmx=True,
        params={"data_path_id": data_path_id},
    )
    assert response.status_code == 204
    assert "data_paths-tab" in response.headers["HX-Redirect"]
    session.expire_all()
    assert session.first(Q.data_path.select(id=data_path_id)) is None


def test_owner_sees_data_without_remove(client: TestClient, owner: Owner, user_token: str):
    if owner.entity == "experiment":
        pytest.skip("experiments are for insiders")
    root = get(client, _browse(owner), user_token)
    assert root.status_code == 200
    assert "runs/run1/" in root.text
    assert "Remove from" not in root.text


def test_other_users_get_nothing(client: TestClient, owner: Owner, user_2_token: str, user_token: str):
    assert get(client, _browse(owner), user_2_token).status_code == 403
    files = f"/htmx/{owner.prefix}/{owner.id}/files/runs/run1/img/plot.png"
    assert get(client, files, user_2_token).status_code == 403
    if owner.entity == "experiment":
        # experiments are for insiders
        assert get(client, _browse(owner), user_token).status_code == 403


def test_remove_needs_admin_or_bioinformatician(
    client: TestClient, session: SyncSession, owner: Owner, insider_token: str, user_token: str,
):
    data_path_id = session.get_one(Q.data_path.select(**{f"{owner.entity}_id": owner.id})).id
    # technicians see the data but no remove menu
    assert "Remove from" not in get(client, _browse(owner), insider_token).text
    for token in (insider_token, user_token):
        response = delete(
            client, f"/htmx/{owner.prefix}/{owner.id}/remove-data_path", token, htmx=True,
            params={"data_path_id": data_path_id},
        )
        assert response.status_code == 403
    assert [dp.path for dp in _paths(session, owner)] == ["runs/run1"]


# Manage data: admins and bioinformaticians tick paths from the whole share to add, untick linked ones to remove

def _save(client: TestClient, owner: Owner, token: str, add: list[str] = (), remove: list[str] = ()):
    fields = {f"add-{i}": path for i, path in enumerate(add)} | {f"remove-{i}": path for i, path in enumerate(remove)}
    return post_form(client, f"/htmx/{owner.prefix}/{owner.id}/data_paths", fields, token, htmx=True)


def _paths(session: SyncSession, owner: Owner) -> list[models.DataPath]:
    session.expire_all()
    return list(session.get_all(Q.data_path.select(**{f"{owner.entity}_id": owner.id}), limit=None))


@pytest.mark.parametrize("token_name, shown", [
    ("admin_token", True), ("bioinformatician_token", True), ("insider_token", False),
])
def test_manage_data_button_for_admins_and_bioinformaticians(
    request, client: TestClient, owner: Owner, token_name: str, shown: bool,
):
    page = get(client, f"/{owner.page}/{owner.id}", request.getfixturevalue(token_name))
    assert page.status_code == 200
    assert (f"/htmx/{owner.prefix}/{owner.id}/manage-data" in page.text) is shown
    if shown:
        assert 'data-bs-target="#fullscreen-modal"' in page.text
        # outside the browser, which leaves the page while the modal is open: a request from a detached
        # button never reaches the document, and the page loader would wait for it forever
        assert page.text.index("/manage-data") < page.text.index('id="file-browser-container"')


def test_picker_browses_the_whole_share(client: TestClient, owner: Owner, bioinformatician_token: str):
    picker = get(client, f"/htmx/{owner.prefix}/{owner.id}/manage-data", bioinformatician_token, htmx=True)
    assert picker.status_code == 200
    assert 'class="modal-content data-picker"' in picker.text
    assert 'data-persist="false"' in picker.text
    assert 'data-allow-roots="false"' in picker.text
    # the linked paths start ticked
    assert """data-initial-paths='["runs/run1"]'""" in picker.text
    assert f'data-owner-label="{_label(owner)}"' in picker.text
    assert f"/htmx/{owner.prefix}/{owner.id}/data_paths" in picker.text
    assert "btn btn-sm btn-success" in picker.text
    assert "/htmx/files/?pick=1" in picker.text or "/htmx/files?pick=1" in picker.text

    # pick mode: the share roots can't be picked, only what is inside them
    roots = get(client, "/htmx/files/", bioinformatician_token, params={"pick": 1})
    assert roots.status_code == 200
    assert "browser-entry-pick" not in roots.text and "cm-callback" not in roots.text
    assert "pick=1" in roots.text  # folders keep the mode

    # inside a root: a checkbox and only Select
    listing = get(client, "/htmx/files/other", bioinformatician_token, params={"pick": 1})
    assert 'data-select-path="other/reports"' in listing.text
    assert "browser-entry-pick" in listing.text
    assert "AssociatePathAction" not in listing.text and "associate-path" not in listing.text


def test_picker_needs_admin_or_bioinformatician(
    client: TestClient, owner: Owner, insider_token: str, user_token: str, user_2_token: str,
):
    for token in (insider_token, user_token, user_2_token):
        assert get(client, f"/htmx/{owner.prefix}/{owner.id}/manage-data", token, htmx=True).status_code == 403


def test_add_data_paths(client: TestClient, session: SyncSession, owner: Owner, bioinformatician_token: str):
    response = _save(client, owner, bioinformatician_token, add=["other/reports/summary.pdf", "other/reports/", "runs/run1"])
    assert response.status_code == 204
    assert "data_paths-tab" in response.headers["HX-Redirect"]

    # the folder covers the file in it, and runs/run1 was already there
    data_paths = {data_path.path: data_path.type for data_path in _paths(session, owner)}
    assert data_paths == {"runs/run1": C.DataPathType.DIRECTORY, "other/reports": C.DataPathType.DIRECTORY}

    # only the owner's tab sees it
    assert "other/reports/" in get(client, _browse(owner), bioinformatician_token).text


def test_add_a_file_infers_its_type(client: TestClient, session: SyncSession, owner: Owner, admin_token: str):
    assert _save(client, owner, admin_token, add=["other/private.pdf"]).status_code == 204
    assert {dp.path: dp.type for dp in _paths(session, owner)}["other/private.pdf"] == C.DataPathType.PDF


def test_unticking_removes_only_that_link(
    client: TestClient, session: SyncSession, owner: Owner, share: Path, bioinformatician_token: str,
):
    # linked meanwhile, e.g. in another tab: not in this picker's changes, so it stays
    other = {owner.entity: session.get_one(getattr(Q, owner.entity).select(id=owner.id))}
    session.save(Q.data_path.create(path="other/private.pdf", type=C.DataPathType.PDF, **other), flush=True)
    session.commit()

    response = _save(client, owner, bioinformatician_token, add=["other/reports"], remove=["runs/run1"])
    assert response.status_code == 204
    assert sorted(dp.path for dp in _paths(session, owner)) == ["other/private.pdf", "other/reports"]
    assert (share / "runs" / "run1").is_dir()  # the files stay


def test_a_path_gone_from_storage_can_still_be_removed(
    client: TestClient, session: SyncSession, owner: Owner, share: Path, bioinformatician_token: str,
):
    (share / "runs" / "run1").rename(share / "runs" / "moved")
    assert _save(client, owner, bioinformatician_token, remove=["runs/run1"]).status_code == 204
    assert _paths(session, owner) == []


def test_nothing_to_save(client: TestClient, session: SyncSession, owner: Owner, bioinformatician_token: str):
    assert _save(client, owner, bioinformatician_token).status_code == 400
    assert [dp.path for dp in _paths(session, owner)] == ["runs/run1"]


@pytest.mark.parametrize("bad", [
    "", ".", "../etc", "/etc", "missing", "other/missing", "other/../other/reports", "runs/../../etc",
    # share roots: only what is inside them can be added
    "other", "other/", "./runs",
])
def test_add_rejects_paths_outside_or_missing(
    client: TestClient, session: SyncSession, owner: Owner, bioinformatician_token: str, bad: str,
):
    # one bad path rejects all the changes
    response = _save(client, owner, bioinformatician_token, add=["other/reports", bad], remove=["runs/run1"])
    assert response.status_code == 400
    assert [dp.path for dp in _paths(session, owner)] == ["runs/run1"]


def test_add_rejects_a_symlink_out_of_the_share(
    client: TestClient, session: SyncSession, owner: Owner, share: Path, tmp_path: Path, bioinformatician_token: str,
):
    (tmp_path / "outside").mkdir()
    (share / "other" / "escape").symlink_to(tmp_path / "outside")
    assert _save(client, owner, bioinformatician_token, add=["other/escape"]).status_code == 400
    assert [dp.path for dp in _paths(session, owner)] == ["runs/run1"]


def test_save_needs_admin_or_bioinformatician(
    client: TestClient, session: SyncSession, owner: Owner, insider_token: str, user_token: str, user_2_token: str,
):
    for token in (insider_token, user_token, user_2_token):
        assert _save(client, owner, token, add=["other/reports"], remove=["runs/run1"]).status_code == 403
    assert [dp.path for dp in _paths(session, owner)] == ["runs/run1"]


def test_full_share_listing_is_for_insiders(client: TestClient, share: Path, user_token: str, insider_token: str):
    assert get(client, "/htmx/files/", user_token).status_code == 403
    assert get(client, "/htmx/files/other", user_token).status_code == 403
    assert get(client, "/htmx/files/", insider_token).status_code == 200
