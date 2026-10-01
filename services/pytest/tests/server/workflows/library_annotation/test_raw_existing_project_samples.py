"""LibraryAnnotationWorkflow: raw samples added to an existing project, reusing one of its samples (10X 5' + VDJ-T)."""

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, libraries_by_name, spreadsheet, spreadsheet_rows

L = C.LibraryType


def test_raw_existing_project_samples_annotation(
    client, session: SyncSession, user, user_token,
):
    project = session.save(Q.project.create(title="Existing Immune Project", description="existing", owner_id=user.id), flush=True)
    existing = session.save(Q.sample.create(name="Existing_1", project_id=project.id, owner_id=user.id, status=C.SampleStatus.DRAFT), flush=True)
    existing.set_attribute(key="sex", value="female", type=C.AttributeType.SEX)
    existing.set_attribute(key="batch", value="B1", type=C.AttributeType.CUSTOM)
    session.save(existing)
    session.commit()
    existing_id = existing.id

    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.post("project-select", {"existing_project": str(project.id)}, next_step="sample-annotation")
    attribute_step = wf.samples([["Existing_1", HUMAN], ["New_1", HUMAN]])
    # The existing sample is recognised and its attributes, including custom ones, are pre-filled in their own columns.
    assert '"Batch"' in attribute_step.text
    rows = {row[0]: row for row in spreadsheet_rows(attribute_step)}
    assert str(rows["Existing_1"][1]) == str(existing_id) and rows["New_1"][1] == "(new)"
    assert "female" in rows["Existing_1"] and "B1" in rows["Existing_1"]
    assert "B1" not in rows["New_1"]

    columns = ["Sample Name", "Sample ID", "Sex", "Batch", "Treatment"]
    wf.post("sample-attribute-annotation", spreadsheet(columns, [
        ["Existing_1", str(existing_id), "female", "B1", "DMSO"], ["New_1", "(new)", "male", "B2", ""],
    ]), status=202)  # custom attribute only partially filled
    wf.post("sample-attribute-annotation", spreadsheet(columns, [
        ["Existing_1", str(existing_id), "female", "B1", "DMSO"], ["New_1", "(new)", "male", "", "Drug_X"],
    ]), status=202)  # existing custom attribute left empty for the new sample
    wf.post("sample-attribute-annotation", spreadsheet(columns, [
        ["Existing_1", str(existing_id), "female", "B1", "  DMSO "], ["New_1", "(new)", "male", "B2", "Drug_X"],
    ]), next_step="select-service")

    wf.service(C.ServiceType.TENX_SC_GEX_5PRIME, next_step="complete-s-a-s", optional_assays__vdj_t="on")
    wf.complete()
    wf.assert_cleaned_up()

    session.expire_all()
    samples = {s.name: s for s in session.get_all(Q.sample.select(project_id=project.id), limit=None)}
    assert set(samples) == {"Existing_1", "New_1"}
    assert samples["Existing_1"].id == existing_id  # reused, not duplicated
    attrs = {name: {a.name: a.value for a in s.attributes} for name, s in samples.items()}
    assert attrs["Existing_1"] == {"sex": "female", "batch": "B1", "treatment": "DMSO"}  # custom keys are lower-cased, values stripped
    assert attrs["New_1"] == {"sex": "male", "batch": "B2", "treatment": "Drug_X"}

    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == {
        f"{s}_{t.identifier}" for s in ["Existing_1", "New_1"] for t in [L.TENX_SC_GEX_5PRIME, L.TENX_VDJ_T]
    }
    assert {link.sample_id for link in libraries[f"Existing_1_{L.TENX_SC_GEX_5PRIME.identifier}"].sample_links} == {existing_id}

    # A second annotation of the same request may not add another 5' GEX library for Existing_1.
    wf2 = AnnotationWorkflow(client, user_token, seq_request.id)
    wf2.begin()
    wf2.post("project-select", {"existing_project": str(project.id)}, next_step="sample-annotation")
    wf2.samples([["Existing_1", HUMAN]])
    wf2.attributes(["Existing_1"])
    wf2.service(
        C.ServiceType.TENX_SC_GEX_5PRIME, next_step="define-multiplexed-samples",
        additional_services__oligo_multiplexing="on", additional_services__oligo_multiplexing_kit="HTO",
    )
    wf2.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"], [["Existing_1", "Rerun_Pool"]],
    ), status=202)  # Existing_1 already has a 5' GEX library in this request
    assert len(libraries_by_name(session, seq_request.id)) == 4
