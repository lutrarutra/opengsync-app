from fastapi.testclient import TestClient

from opengsync_db import SyncSession

from ..db.create_units import create_project
from ._http import auth


def test_project_software_api_upserts_and_deletes(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    project = create_project(session, insider)
    session.commit()

    response = client.post(
        "/api/projects/add-software",
        json={
            "project_id": project.id,
            "software": " ATACSeq_Pipeline ",
            "version": "v1",
            "comment": "initial",
        },
        headers=auth(insider_token),
    )
    assert response.status_code == 200
    assert response.json()["software"]["atacseq_pipeline"]["version"] == "v1"

    response = client.post(
        "/api/projects/add-software",
        json={
            "project_id": project.id,
            "software": "atacseq_pipeline",
            "version": "v2",
        },
        headers=auth(insider_token),
    )
    assert response.status_code == 200
    software = response.json()["software"]
    assert list(software) == ["atacseq_pipeline"]
    assert software["atacseq_pipeline"]["version"] == "v2"
    assert "comment" not in software["atacseq_pipeline"]

    response = client.request(
        "DELETE",
        "/api/projects/delete-software",
        json={"project_id": project.id, "software": " ATACSEQ_PIPELINE "},
        headers=auth(insider_token),
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert response.json()["software"] == {}

    response = client.request(
        "DELETE",
        "/api/projects/delete-software",
        json={"project_id": project.id, "software": "atacseq_pipeline"},
        headers=auth(insider_token),
        follow_redirects=False,
    )
    assert response.status_code == 404


def test_project_software_api_requires_insider(
    client: TestClient,
    user_token: str,
):
    response = client.post(
        "/api/projects/add-software",
        json={
            "project_id": 1,
            "software": "software",
            "version": "v1",
        },
        headers=auth(user_token),
    )

    assert response.status_code == 403
