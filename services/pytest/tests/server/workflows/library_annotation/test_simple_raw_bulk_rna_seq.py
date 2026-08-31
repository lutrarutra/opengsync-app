"""LibraryAnnotationWorkflow: raw-samples bulk RNA-seq happy path and validation."""

import uuid
from typing import Any

from redis import Redis

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ....db.create_units import create_seq_request, create_project
from ..._http import get, post_form, spreadsheet_payload, OpenGSyncTestClient


def test_simple_raw_bulk_rna_seq_annotation(
    client: OpenGSyncTestClient, session: SyncSession, user, user_2, user_token,
):
    own_processing = create_project(session, user)
    own_processing.status = C.ProjectStatus.PROCESSING
    session.save(own_processing)
    stranger_draft = create_project(session, user_2)
    duplicate_title = "Already Owned Project Title"
    session.save(Q.project.create(
        title=duplicate_title, description="existing", owner_id=user.id,
    ), flush=True)
    session.commit()

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

    post("project-select", {}, status=202)  # neither existing nor new project
    post("project-select", {"new_project": "A Valid Project Title"}, status=202)  # new project without description
    post("project-select", {
        "new_project": "A Valid Project Title",
        "project_description": "   ",
    }, status=202)  # whitespace-only description
    post("project-select", {
        "new_project": "Short",
        "project_description": "A brief description of the project.",
    }, status=202)  # title shorter than 6 characters
    post("project-select", {
        "new_project": "T" * (models.Project.title.type.length + 1),
        "project_description": "A brief description of the project.",
    }, status=202)  # title longer than max length
    post("project-select", {
        "new_project": "AAAAAA",
        "project_description": "D" * 2049,
    }, status=202)  # description longer than 2048 characters
    post("project-select", {
        "new_project": duplicate_title,
        "project_description": "A brief description of the project.",
    }, status=202)  # owner already has a project with this title
    post("project-select", {"existing_project": "999999"}, status=404)  # existing project id does not exist
    post("project-select", {"existing_project": str(stranger_draft.id)}, status=202)  # no write access to another user's project
    post("project-select", {"existing_project": str(own_processing.id)}, status=202)  # no write access once project is not DRAFT

    project_title = "BULK RNA-seq Project from raw samples test"
    post("project-select", {
        "new_project": project_title,
        "project_description": "test project for raw sample submission, simple",
    })
    assert session.first(Q.project.select(title=project_title)) is None

    human = C.GenomeRef.HUMAN.display_name
    sample_columns = ["Sample Name", "Genome"]
    sample_name_max = models.Sample.name.type.length

    post("sample-annotation", spreadsheet_payload(sample_columns, []), status=202)  # empty spreadsheet
    post("sample-annotation", {"spreadsheet": "[]"}, status=202)  # missing columns payload
    post("sample-annotation", {
        "spreadsheet": "not-json",
        "columns": '["Sample Name", "Genome"]',
    }, status=202)  # invalid spreadsheet JSON
    post("sample-annotation", spreadsheet_payload(["Genome"], [[human]]), status=202)  # missing Sample Name column
    post("sample-annotation", spreadsheet_payload(["Sample Name"], [["Sample_A"]]), status=202)  # missing Genome column
    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["", human],
        ["Sample_B", human],
    ]), status=202)  # empty sample name
    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["   ", human],
        ["Sample_B", human],
    ]), status=202)  # whitespace-only sample name
    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["abc", human],
        ["Sample_B", human],
    ]), status=202)  # sample name shorter than 4 characters
    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["A" * (sample_name_max + 1), human],
        ["Sample_B", human],
    ]), status=202)  # sample name longer than max length
    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["Sample.A", human],
        ["Sample_B", human],
    ]), status=202)  # '.' is not allowed in sample names
    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["Sample_A", ""],
        ["Sample_B", human],
    ]), status=202)  # missing genome
    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["Sample_A", "Martian"],
        ["Sample_B", human],
    ]), status=202)  # genome is not a known reference
    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["Sample_B", human],
        ["Sample_B", human],
    ]), status=202)  # duplicate sample names
    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["Sample A", human],
        ["Sample_A", human],
    ]), status=202)  # names collide after spaces are replaced with '_'
    assert session.count(Q.library.select(seq_request_id=seq_request.id)) == 0

    post("sample-annotation", spreadsheet_payload(sample_columns, [
        ["Sample_A", human],
        ["Sample_B", human],
    ]))

    attribute_columns = ["Sample Name", "Sample ID", "Test Attribute"]
    post("sample-attribute-annotation", spreadsheet_payload(attribute_columns, []), status=202)  # empty spreadsheet
    post("sample-attribute-annotation", spreadsheet_payload(["Sample Name"], [
        ["Sample_A"],
        ["Sample_B"],
    ]), status=202)  # missing required Sample ID column
    post("sample-attribute-annotation", spreadsheet_payload(
        ["Sample Name", "Sample ID", "xy"],
        [
            ["Sample_A", "(new)", "value"],
            ["Sample_B", "(new)", "value"],
        ],
    ), status=202)  # attribute column name shorter than 3 characters
    post("sample-attribute-annotation", spreadsheet_payload(attribute_columns, [
        ["Sample_A", "(new)", "Test Attribute A"],
    ]), status=202)  # a sample from the previous step is missing
    post("sample-attribute-annotation", spreadsheet_payload(attribute_columns, [
        ["Sample_A", "(new)", "Test Attribute A"],
        ["Sample_B", "(new)", ""],
    ]), status=202)  # attribute column is only partially filled
    post("sample-attribute-annotation", spreadsheet_payload(
        ["Sample Name", "Sample ID", "Sex"],
        [
            ["Sample_A", "(new)", "V" * (models.SampleAttribute.MAX_NAME_LENGTH + 1)],
            ["Sample_B", "(new)", "ok"],
        ],
    ), status=202)  # attribute value longer than max length

    post("sample-attribute-annotation", spreadsheet_payload(attribute_columns, [
        ["Sample_A", "(new)", "Test Attribute A"],
        ["Sample_B", "(new)", "Test Attribute B"],
    ]))

    post("select-service", {}, status=202)  # service type is required
    post("select-service", {"service_type": "99999"}, status=202)  # service type is not a known assay
    post("select-service", {
        "service_type": str(C.ServiceType.BULK_RNA_SEQ.id),
        "optional_assays-antibody_capture": "on",
    }, status=202)  # antibody capture requires a kit name
    post("select-service", {
        "service_type": str(C.ServiceType.BULK_RNA_SEQ.id),
        "optional_assays-antibody_multiplexing": "on",
    }, status=202)  # antibody hashing requires cell surface protein capture
    post("select-service", {
        "service_type": str(C.ServiceType.BULK_RNA_SEQ.id),
        "optional_assays-parse_mux": "on",
    }, status=202)  # Parse multiplexing is only valid with Parse assays
    post("select-service", {
        "service_type": str(C.ServiceType.BULK_RNA_SEQ.id),
        "optional_assays-antibody_capture": "on",
        "optional_assays-antibody_capture_kit": "Hashing kit",
        "optional_assays-antibody_multiplexing": "on",
        "additional_services-oligo_multiplexing": "on",
        "additional_services-oligo_multiplexing_kit": "CMO kit",
    }, status=202)  # cannot combine antibody hashing and oligo multiplexing
    post("select-service", {
        "service_type": str(C.ServiceType.BULK_RNA_SEQ.id),
        "additional_services-oligo_multiplexing": "on",
        "additional_services-oligo_multiplexing_kit": "CMO kit",
        "additional_services-ocm_multiplexing": "on",
    }, status=202)  # cannot combine oligo and on-chip multiplexing
    post("select-service", {
        "service_type": str(C.ServiceType.PARSE.id),
        "optional_assays-parse_kit": "-1",
        "optional_assays-parse_chemistry": "-1",
    }, status=202)  # Parse assay requires kit and chemistry
    post("select-service", {
        "service_type": str(C.ServiceType.BULK_RNA_SEQ.id),
        "additional_services-oligo_multiplexing": "on",
    }, status=202)  # oligo multiplexing requires a kit name

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
