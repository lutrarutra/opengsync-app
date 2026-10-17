"""LibraryAnnotationWorkflow sample annotation: samples of the selected project are picked by id, other names are new samples."""

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, spreadsheet, spreadsheet_rows

COLUMNS = ["Sample Name", "Organism"]


def test_existing_samples_by_id_and_new_samples_by_name(client, session: SyncSession, user, user_token):
    project = session.save(Q.project.create(title="Query Column Project", description="existing", owner_id=user.id), flush=True)
    existing = session.save(Q.sample.create(name="Existing_1", project_id=project.id, owner_id=user.id, status=C.SampleStatus.DRAFT), flush=True)
    rejected = session.save(Q.sample.create(name="Failed_1", project_id=project.id, owner_id=user.id, status=C.SampleStatus.REJECTED), flush=True)
    other_project = session.save(Q.project.create(title="Other Project", description="other", owner_id=user.id), flush=True)
    other = session.save(Q.sample.create(name="Other_1", project_id=other_project.id, owner_id=user.id, status=C.SampleStatus.DRAFT), flush=True)
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    step = wf.post("project-select", {"project": str(project.id)}, next_step="sample-annotation")
    # The editor searches the samples of the project and offers to create new ones
    assert f"/htmx/samples/query?project_id={project.id}" in step.text
    assert "allowNew: true" in step.text

    wf.post("sample-annotation", spreadsheet(COLUMNS, [[rejected.id, HUMAN], ["New_1", HUMAN]]), status=202)
    wf.post("sample-annotation", spreadsheet(COLUMNS, [[other.id, HUMAN], ["New_1", HUMAN]]), status=202)
    wf.post("sample-annotation", spreadsheet(COLUMNS, [[existing.id, HUMAN], ["Existing_1", HUMAN]]), status=202)  # same sample twice
    wf.post("sample-annotation", spreadsheet(COLUMNS, [[existing.id, HUMAN], ["abc", HUMAN]]), status=202)  # new name too short

    attribute_step = wf.post(
        "sample-annotation", spreadsheet(COLUMNS, [[existing.id, HUMAN], [" New 1 ", HUMAN]]),
        next_step="sample-attribute-annotation",
    )
    # The existing sample keeps its id, the new one is cleaned up like the sample names before
    assert sorted(row[0] for row in spreadsheet_rows(attribute_step)) == [f"Existing_1 [{existing.id}]", "New_1 [new]"]
    # The read-only sample column only takes the samples of the previous step
    wf.post("sample-attribute-annotation", spreadsheet(["Sample"], [[f"Existing_1 [{existing.id}]"], ["Other_1 [new]"]]), status=202)
    wf.post("sample-attribute-annotation", spreadsheet(["Sample"], [[f"Other_1 [{other.id}]"], ["New_1 [new]"]]), status=202)

    # Back to the samples: the existing sample keeps its id, the new one its name
    back = wf.back("sample-annotation")
    assert spreadsheet_rows(back) == [[existing.id, HUMAN], ["New_1", HUMAN]]
    assert f'"{existing.id}": "Existing_1"' in back.text  # the editor shows the name of the id


def test_new_project_samples_are_all_new(client, session: SyncSession, user, user_token):
    project = session.save(Q.project.create(title="Not Selected Project", description="existing", owner_id=user.id), flush=True)
    sample = session.save(Q.sample.create(name="Existing_1", project_id=project.id, owner_id=user.id, status=C.SampleStatus.DRAFT), flush=True)
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    step = wf.project("Brand New Project")
    assert "url: null" in step.text  # nothing to search

    wf.post("sample-annotation", spreadsheet(COLUMNS, [[sample.id, HUMAN]]), status=202)  # not a sample of the project
    attribute_step = wf.samples([["Existing_1", HUMAN]])
    assert spreadsheet_rows(attribute_step)[0][0] == "Existing_1 [new]"
