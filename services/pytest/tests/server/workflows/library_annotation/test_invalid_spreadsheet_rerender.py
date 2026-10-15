"""LibraryAnnotationWorkflow: an invalid spreadsheet is rendered again as submitted, every cell under its column.

Errors are found by the spreadsheet validation (rendered from the submitted cells) or by the route after it (rendered
from the validated data, where the sample column is split into its id and name columns).
"""

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, MOUSE, spreadsheet, spreadsheet_records

SAMPLE_COLUMNS = ["Sample Name", "Organism"]


def _workflow(client, session: SyncSession, user, user_token):
    project = session.save(Q.project.create(title="Rerender Project", description="existing", owner_id=user.id), flush=True)
    existing = session.save(Q.sample.create(name="Existing_1", project_id=project.id, owner_id=user.id, status=C.SampleStatus.DRAFT), flush=True)
    session.save(Q.sample.create(name="Failed_1", project_id=project.id, owner_id=user.id, status=C.SampleStatus.REJECTED), flush=True)
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.post("project-select", {"existing_project": str(project.id)}, next_step="sample-annotation")
    return wf, existing.id


def _submitted(columns: list[str], rows: list[list]) -> list[dict]:
    return [dict(zip(columns, row)) for row in rows]


def test_sample_annotation_rerenders_invalid_spreadsheet(client, session: SyncSession, user, user_token):
    wf, existing_id = _workflow(client, session, user, user_token)

    # Invalid cell (name too short): the submitted cells
    rows = [[existing_id, HUMAN], ["abc", MOUSE]]
    response = wf.post("sample-annotation", spreadsheet(SAMPLE_COLUMNS, rows), status=202)
    assert spreadsheet_records(response) == _submitted(SAMPLE_COLUMNS, rows)

    # Rejected project sample (found by the route): the validated cells, without the sample name column of the data
    rows = [[existing_id, HUMAN], ["Failed_1", MOUSE]]
    response = wf.post("sample-annotation", spreadsheet(SAMPLE_COLUMNS, rows), status=202)
    assert "is rejected" in response.text
    assert spreadsheet_records(response) == _submitted(SAMPLE_COLUMNS, rows)


def test_sample_attribute_annotation_rerenders_invalid_spreadsheet(client, session: SyncSession, user, user_token):
    wf, existing_id = _workflow(client, session, user, user_token)
    attribute_step = wf.samples([["Existing_1", HUMAN], ["New_1", HUMAN]])
    defined = list(spreadsheet_records(attribute_step)[0].keys())
    assert defined[:2] == ["Sample", "Sex"]

    # A column added by the user, and the attributes not in the order of the columns
    columns = ["Sample", "Tissue", "Sex", "Source"]
    rows = [[f"Existing_1 [{existing_id}]", "skin", "F", "Daniel Mayr"], ["New_1 [new]", "", "", ""]]

    def expected(rows: list[list]) -> list[dict]:
        return [{title: "" for title in defined} | record for record in _submitted(columns, rows)]

    # Missing values (found by the route after the validation): the added column is kept
    response = wf.post("sample-attribute-annotation", spreadsheet(columns, rows), status=202)
    assert "Missing value" in response.text
    assert spreadsheet_records(response) == expected(rows)

    # Unknown sample (found by the validation): the submitted cells, the added column keeps its title
    invalid = [["Other_1 [new]", *rows[0][1:]], rows[1]]
    response = wf.post("sample-attribute-annotation", spreadsheet(columns, invalid), status=202)
    assert "Invalid value" in response.text
    assert spreadsheet_records(response) == expected(invalid)

    # The corrected spreadsheet is accepted
    valid = [rows[0], ["New_1 [new]", "liver", "M", "Daniel Mayr"]]
    wf.post("sample-attribute-annotation", spreadsheet(columns, valid), next_step="select-service")
