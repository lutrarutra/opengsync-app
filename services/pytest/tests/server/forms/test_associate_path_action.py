"""AssociatePathAction: link a share-root path to a project/experiment/request/library.

Share-root escape attempts are covered in ``server/test_share_root_abuse.py``.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q

from server.core import config

from ...db.create_units import create_project
from .._http import post_form

SUBMIT_PATH = "/htmx/files/associate-path"


@pytest.fixture
def share_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "share"
    (root / "results").mkdir(parents=True)
    (root / "results" / "report.html").write_text("<html></html>")
    monkeypatch.setattr(config.settings.app_config, "share_root", str(root))
    return root


def _data_paths(session: SyncSession, path: str) -> list:
    session.expire_all()
    return list(session.get_all(Q.data_path.select(path=path), limit=None))


def test_submit_associates_path_with_project(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
    share_root: Path,
):
    project = create_project(session, user)
    session.commit()

    response = post_form(
        client, SUBMIT_PATH, {"project": project.id},
        token=insider_token, params={"path": "results/report.html"},
    )

    # Empty OK response; the form closes its modal, and the browser updates the row's badges from HX-Trigger.
    assert response.status_code == 204
    assert "HX-Redirect" not in response.headers
    events = json.loads(response.headers["HX-Trigger"])
    assert events["dataPathAssociationsUpdated"]["path"] == "results/report.html"
    [association] = events["dataPathAssociationsUpdated"]["associations"]
    assert association["label"] == (project.identifier or project.title)
    assert association["href"].endswith(f"/{project.id}")

    [data_path] = _data_paths(session, "results/report.html")
    assert data_path.project_id == project.id


def test_submit_requires_insider(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
    share_root: Path,
):
    project = create_project(session, user)
    session.commit()

    response = post_form(
        client, SUBMIT_PATH, {"project": project.id},
        token=user_token, params={"path": "results/report.html"},
    )

    assert response.status_code == 403
    assert _data_paths(session, "results/report.html") == []



# ── Targets, types, duplicates ──────────────────────────────────────────────


@pytest.fixture
def targets(session: SyncSession, user, insider) -> dict:
    from opengsync_db import categories as C
    from ...db.create_units import create_experiment, create_library, create_seq_request

    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    experiment = create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_6K_SP_XP)
    project = create_project(session, user)
    session.commit()
    return {"project": project, "experiment": experiment, "seq_request": seq_request, "library": library}


def _associate(client: TestClient, token: str, path: str, **fields):
    return post_form(client, SUBMIT_PATH, {key: str(value.id) for key, value in fields.items()}, token=token, params={"path": path})


@pytest.mark.parametrize("target", ["experiment", "seq_request", "library"])
def test_submit_associates_path_with_each_target(
    client: TestClient, session: SyncSession, insider_token: str, share_root: Path, targets: dict, target: str,
):
    response = _associate(client, insider_token, "results/report.html", **{target: targets[target]})

    assert response.status_code == 204, response.text
    [data_path] = _data_paths(session, "results/report.html")
    assert getattr(data_path, f"{target}_id") == targets[target].id
    [association] = json.loads(response.headers["HX-Trigger"])["dataPathAssociationsUpdated"]["associations"]
    assert association["label"] == targets[target].name


def test_submit_associates_several_targets_at_once(
    client: TestClient, session: SyncSession, insider_token: str, share_root: Path, targets: dict,
):
    response = _associate(client, insider_token, "results", **targets)

    assert response.status_code == 204, response.text
    data_paths = _data_paths(session, "results")
    assert len(data_paths) == 4
    assert len(json.loads(response.headers["HX-Trigger"])["dataPathAssociationsUpdated"]["associations"]) == 4


@pytest.mark.parametrize("path, expected", [
    ("results", "DIRECTORY"),
    ("results/report.html", "HTML"),
    ("results/table.tsv", "TABLE"),
    ("results/summary.pdf", "PDF"),
    ("results/plot.png", "IMAGE"),
    ("results/sheet.xlsx", "EXCEL"),
    ("results/notes.txt", "CUSTOM"),
])
def test_path_type_follows_the_file(
    client: TestClient, session: SyncSession, insider_token: str, share_root: Path, targets: dict, path: str, expected: str,
):
    from opengsync_db import categories as C

    if not (share_root / path).exists():
        (share_root / path).write_text("x")

    _associate(client, insider_token, path, project=targets["project"])

    [data_path] = _data_paths(session, path)
    assert data_path.type == getattr(C.DataPathType, expected)


def test_associating_the_same_path_twice_keeps_one_link(
    client: TestClient, session: SyncSession, insider_token: str, share_root: Path, targets: dict,
):
    """Legacy meant to skip existing links (``LinkAlreadyExists``), but that was never raised, so it stored duplicates."""
    _associate(client, insider_token, "results/report.html", project=targets["project"])

    response = _associate(client, insider_token, "results/report.html", project=targets["project"], library=targets["library"])

    assert response.status_code == 204
    data_paths = _data_paths(session, "results/report.html")
    assert {(dp.project_id, dp.library_id) for dp in data_paths} == {(targets["project"].id, None), (None, targets["library"].id)}
    assert len(data_paths) == 2
    assert len(json.loads(response.headers["HX-Trigger"])["dataPathAssociationsUpdated"]["associations"]) == 2


def test_same_path_may_be_linked_to_different_projects(
    client: TestClient, session: SyncSession, user, insider_token: str, share_root: Path, targets: dict,
):
    other = create_project(session, user)
    session.commit()

    _associate(client, insider_token, "results/report.html", project=targets["project"])
    _associate(client, insider_token, "results/report.html", project=other)

    assert sorted(dp.project_id for dp in _data_paths(session, "results/report.html")) == sorted([targets["project"].id, other.id])


def test_unknown_target_is_404_and_saves_nothing(
    client: TestClient, session: SyncSession, insider_token: str, share_root: Path, targets: dict,
):
    response = post_form(
        client, SUBMIT_PATH, {"project": str(targets["project"].id), "library": "999999"},
        token=insider_token, params={"path": "results/report.html"},
    )

    assert response.status_code == 404
    assert _data_paths(session, "results/report.html") == []


def test_no_target_saves_nothing(client: TestClient, session: SyncSession, insider_token: str, share_root: Path):
    """As legacy: nothing selected is accepted and does nothing."""
    response = post_form(client, SUBMIT_PATH, {}, token=insider_token, params={"path": "results/report.html"})

    assert response.status_code == 204
    assert _data_paths(session, "results/report.html") == []


def test_render_requires_insider(client: TestClient, user_token: str, insider_token: str, share_root: Path):
    from .._http import get

    assert get(client, SUBMIT_PATH, user_token, params={"path": "results"}).status_code == 403
    assert get(client, SUBMIT_PATH, insider_token, params={"path": "results"}).status_code == 200
