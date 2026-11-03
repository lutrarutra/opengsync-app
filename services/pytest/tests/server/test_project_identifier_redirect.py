"""/projects/i/{identifier} redirects to the project page by id; unknown identifiers 404."""

import uuid

from fastapi.testclient import TestClient

from opengsync_db import SyncSession

from ..db.create_units import create_project
from ._http import get


def test_identifier_redirects_to_project_page(client: TestClient, session: SyncSession, user, user_token):
    project = create_project(session, user)
    project.identifier = f"T_{uuid.uuid4().hex[:10]}"
    session.save(project)
    session.commit()

    response = get(client, f"/projects/i/{project.identifier}", user_token)

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/projects/{project.id}")


def test_unknown_identifier_returns_404(client: TestClient, user_token):
    response = get(client, f"/projects/i/NOPE_{uuid.uuid4().hex[:8]}", user_token)

    assert response.status_code == 404
