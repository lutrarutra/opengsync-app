"""LibraryAnnotationWorkflow: raw samples, custom service with library types chosen per sample."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, MOUSE, libraries_by_name, linked_samples, spreadsheet, spreadsheet_rows

L = C.LibraryType
LABEL = dict(C.LibraryType.as_selectable())  # the dropdown submits display labels


def test_raw_custom_assay_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Custom assay raw samples")
    wf.samples([["Custom_A", HUMAN], ["Custom_B", MOUSE]])
    wf.attributes(["Custom_A", "Custom_B"])

    custom_step = wf.service(
        C.ServiceType.CUSTOM, next_step="custom-assay-annotation",
        additional_info="Please use 2x150 for the amplicons.",
    )
    assert sorted(row[0] for row in spreadsheet_rows(custom_step)) == ["Custom_A", "Custom_B"]
    assert wf.back_step(custom_step) == "select-service"

    columns = ["Sample Name (Pool)", "Library Type"]
    wf.post("custom-assay-annotation", spreadsheet(columns, [
        ["Custom_A", LABEL[L.SMART_SC_SEQ.id]],
    ]), status=202)  # Custom_B has no library type
    wf.post("custom-assay-annotation", spreadsheet(columns, [
        ["Custom_A", LABEL[L.SMART_SC_SEQ.id]],
        ["Custom_A", LABEL[L.SMART_SC_SEQ.id]],
        ["Custom_B", LABEL[L.CUT_AND_RUN.id]],
    ]), status=202)  # same library type twice for one sample
    wf.post("custom-assay-annotation", spreadsheet(columns, [
        ["Custom_A", LABEL[L.TENX_MUX_OLIGO.id]],
        ["Custom_B", LABEL[L.CUT_AND_RUN.id]],
    ]), status=202)  # multiplexing-oligo library without oligo multiplexing
    wf.post("custom-assay-annotation", spreadsheet(columns, [
        ["Unknown", LABEL[L.SMART_SC_SEQ.id]],
        ["Custom_B", LABEL[L.CUT_AND_RUN.id]],
    ]), status=202)  # sample not annotated before
    wf.post("custom-assay-annotation", spreadsheet(columns, [
        ["Custom_A", LABEL[L.SMART_SC_SEQ.id]],
        ["Custom_A", LABEL[L.AMPLICON_SEQ.id]],
        ["Custom_B", LABEL[L.CUT_AND_RUN.id]],
    ]), next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    assert {name: lib.type for name, lib in libraries.items()} == {
        f"Custom_A_{L.SMART_SC_SEQ.identifier}": L.SMART_SC_SEQ,
        f"Custom_A_{L.AMPLICON_SEQ.identifier}": L.AMPLICON_SEQ,
        f"Custom_B_{L.CUT_AND_RUN.identifier}": L.CUT_AND_RUN,
    }
    for name, library in libraries.items():
        sample = "Custom_A" if name.startswith("Custom_A") else "Custom_B"
        assert library.service_type == C.ServiceType.CUSTOM
        assert library.genome_ref == (C.GenomeRef.HUMAN if sample == "Custom_A" else C.GenomeRef.MOUSE)
        assert library.mux_type is None
        assert linked_samples(library) == {sample: None}

    session.refresh(seq_request)
    assert any("Please use 2x150 for the amplicons." in c.text for c in seq_request.comments)
