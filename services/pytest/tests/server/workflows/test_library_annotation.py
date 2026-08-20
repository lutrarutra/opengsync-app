"""LibraryAnnotationWorkflow: raw-samples bulk RNA-seq happy path and validation."""

import uuid
from typing import Any

from redis import Redis

from opengsync_db import SyncSession, queries as Q, categories as C

from ...db.create_units import create_seq_request
from .._http import get, post_form, spreadsheet_payload, OpenGSyncTestClient


def test_simple_raw_bulk_rna_seq_annotation(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    wf_uuid = str(uuid.uuid4())
    params = {"uuid": wf_uuid}
    prefix = f"/htmx/workflows/library-annotation/{seq_request.id}"

    def post(step: str, data: dict[str, Any] | None = None, status: int = 200):
        response = post_form(
            client, f"{prefix}/{step}", data or {},
            token=user_token, params=params,
        )
        assert response.status_code == status
        return response

    begun = get(client, f"{prefix}/begin", user_token, params=params)
    assert begun.status_code == 200

    post("project-select", {}, status=202)

    project_title = "BULK RNA-seq Project from raw samples test"
    post("project-select", {"new_project": project_title}, status=202)
    assert session.first(Q.project.select(title=project_title)) is None

    project_description = "test project for raw sample submission, simple"
    post("project-select", {
        "new_project": project_title,
        "project_description": project_description,
    })

    human = C.GenomeRef.HUMAN.display_name
    sample_columns = ["Sample Name", "Genome"]
    post("sample-annotation", spreadsheet_payload(sample_columns, []), status=202)

    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["Sample_A", ""],
        ["Sample_B", human],
    ]), status=202)

    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["a", human],
        ["Sample_B", human],
    ]), status=202)
    assert session.count(Q.library.select(seq_request_id=seq_request.id)) == 0

    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["Sample_B", human],
        ["Sample_B", human],
    ]), status=202)

    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["Sample_A", human],
        ["Sample_B", human],
    ]))

    attribute_columns = ["Sample Name", "Sample ID", "Test Attribute"]
    post("sample-attribute-annotation", spreadsheet_payload(attribute_columns, [
        ["Sample_A", "(new)", "Test Attribute A"],
        ["Sample_B", "(new)", ""],
    ]), status=202)

    post("sample-attribute-annotation", spreadsheet_payload(attribute_columns, [
        ["Sample_A", "(new)", "Test Attribute A"],
        ["Sample_B", "(new)", "Test Attribute B"],
    ]))

    post("select-service", {"service_type": str(C.ServiceType.BULK_RNA_SEQ.id)})

    complete = post("complete-s-a-s", status=204)
    assert "HX-Redirect" in complete.headers

    session.expire_all()
    created_project = session.first(Q.project.select(title=project_title))
    assert created_project is not None

    samples_in_project = session.get_all(Q.sample.select(project_id=created_project.id), limit=None)
    assert len(samples_in_project) == 2
    assert samples_in_project[0].name == "Sample_A"
    assert samples_in_project[1].name == "Sample_B"

    libraries = session.get_all(Q.library.select(seq_request_id=seq_request.id), limit=None)
    assert len(libraries) == 2
    assert libraries[0].name == f"Sample_A_{C.LibraryType.BULK_RNA_SEQ.identifier}"
    assert libraries[1].name == f"Sample_B_{C.LibraryType.BULK_RNA_SEQ.identifier}"

    leftover = Redis(connection_pool=client.app.state.redis_pool).keys(
        f"LibraryAnnotationWorkflow:{wf_uuid}:*"
    )
    assert leftover == []

    session.refresh(seq_request)
    assert seq_request.num_pools == 0
