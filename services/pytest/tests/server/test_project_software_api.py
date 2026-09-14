from fastapi.testclient import TestClient

from opengsync_db import models, SyncSession
from opengsync_db.categories import DataPathType

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


def test_project_data_paths_api_filters_and_resolves(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
    monkeypatch,
):
    project = create_project(session, insider)
    session.add_all([
        models.DataPath(
            path="BSF_PROJECTS/project",
            project_id=project.id,
            type_id=DataPathType.DIRECTORY.id,
        ),
        models.DataPath(
            path="BSF_PROJECTS/project/subdirectory",
            project_id=project.id,
            type_id=DataPathType.DIRECTORY.id,
        ),
        models.DataPath(
            path="BSF_SEQUENCES/run",
            project_id=project.id,
            type_id=DataPathType.DIRECTORY.id,
        ),
    ])
    session.commit()

    from server.core import config
    from server.core.config import SharePathMapping

    monkeypatch.setattr(
        config.settings.app_config,
        "share_path_mapping",
        SharePathMapping(
            BSF_PROJECTS="/projects",
            BSF_SEQUENCES="/sequences",
            BSF_SEQUENCES_10X="/sequences_10x",
        ),
    )

    response = client.get(
        f"/api/projects/{project.id}/data-paths",
        headers=auth(insider_token),
    )

    assert response.status_code == 200
    assert response.json() == ["/sequences/run", "/projects/project"]


def test_project_data_paths_api_handles_missing_project(
    client: TestClient,
    insider_token: str,
):
    response = client.get(
        "/api/projects/999999/data-paths",
        headers=auth(insider_token),
    )

    assert response.status_code == 404
