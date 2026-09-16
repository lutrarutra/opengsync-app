from fastapi.testclient import TestClient

from opengsync_db import models, SyncSession
from opengsync_db.categories import DataPathType

from ..db.create_units import create_library, create_project, create_seq_request
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
    assert response.json()["detail"] == f"Software 'atacseq_pipeline' not found on project '{project.id}'."


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
    assert response.json()["detail"] == "Permission denied"


def test_library_qc_api_upserts_and_deletes(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    seq_request = create_seq_request(session, insider)
    library = create_library(session, insider, seq_request)
    session.commit()

    response = client.post(
        "/api/libraries/add-qc",
        json={
            "library_id": library.id,
            "qc": {"yield": 10, "purity": 0.95},
        },
        headers=auth(insider_token),
    )
    assert response.status_code == 200
    assert response.json()["qc"] == {"yield": 10, "purity": 0.95}

    response = client.post(
        "/api/libraries/add-qc",
        json={
            "library_id": library.id,
            "qc": {"yield": 12, "quality": "pass"},
        },
        headers=auth(insider_token),
    )
    assert response.status_code == 200
    assert response.json()["qc"] == {"yield": 12, "purity": 0.95, "quality": "pass"}

    response = client.request(
        "DELETE",
        "/api/libraries/delete-qc",
        json={"library_id": library.id, "keys": ["purity", "quality"]},
        headers=auth(insider_token),
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert response.json()["qc"] == {"yield": 12}

    response = client.request(
        "DELETE",
        "/api/libraries/delete-qc",
        json={"library_id": library.id, "keys": ["missing"]},
        headers=auth(insider_token),
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == f"QC key 'missing' not found on library '{library.id}'."

    response = client.request(
        "DELETE",
        "/api/libraries/delete-qc",
        json={"library_id": library.id, "keys": ["yield"]},
        headers=auth(insider_token),
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert response.json()["qc"] == {}


def test_library_qc_api_handles_missing_values(
    client: TestClient,
    insider_token: str,
):
    response = client.post(
        "/api/libraries/add-qc",
        json={"library_id": 999999, "qc": {"yield": 10}},
        headers=auth(insider_token),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Library with ID '999999' not found."

    response = client.request(
        "DELETE",
        "/api/libraries/delete-qc",
        json={"library_id": 999999, "keys": ["yield"]},
        headers=auth(insider_token),
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Library with ID '999999' not found."


def test_library_qc_api_requires_insider(
    client: TestClient,
    user_token: str,
):
    response = client.post(
        "/api/libraries/add-qc",
        json={"library_id": 1, "qc": {"yield": 10}},
        headers=auth(user_token),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


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
        models.DataPath(
            path="BSF_SAMPLES/sample",
            project_id=project.id,
            type_id=DataPathType.DIRECTORY.id,
        ),
    ])
    session.commit()

    from server.core import config

    monkeypatch.setattr(
        config.settings.app_config,
        "share_path_mapping",
        {
            "BSF_PROJECTS": "/projects",
            "BSF_SEQUENCES": "/sequences",
            "BSF_SEQUENCES_10X": "/sequences_10x",
            "BSF_SAMPLES": "/samples",
        },
    )

    response = client.get(
        f"/api/projects/{project.id}/data-paths",
        headers=auth(insider_token),
    )

    assert response.status_code == 200
    assert response.json() == ["/sequences/run", "/samples/sample", "/projects/project"]


def test_project_data_paths_api_handles_missing_project(
    client: TestClient,
    insider_token: str,
):
    response = client.get(
        "/api/projects/999999/data-paths",
        headers=auth(insider_token),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project with ID '999999' not found."
