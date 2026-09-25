"""AssociatePathAction: link a share-root path to a project/experiment/request/library.

Share-root escape attempts are covered in ``server/test_share_root_abuse.py``.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q

from server.core import config

from ...db.create_units import create_project
from .._http import assert_htmx_redirect, post_form

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

    assert_htmx_redirect(response, "/browser/")
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

