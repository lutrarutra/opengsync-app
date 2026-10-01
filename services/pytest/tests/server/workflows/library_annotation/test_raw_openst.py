"""LibraryAnnotationWorkflow: raw samples, Open Spatial Transcriptomics (Open-ST) with image annotation."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, MOUSE, libraries_by_name, linked_samples, spreadsheet, spreadsheet_rows

L = C.LibraryType


def test_raw_openst_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Open-ST raw samples")
    wf.samples([["Brain_Section_1", MOUSE], ["Brain_Section_2", MOUSE]])
    wf.attributes(["Brain_Section_1", "Brain_Section_2"])

    openst_step = wf.service(C.ServiceType.OPENST, next_step="open-s-t-annotation")
    assert sorted(row[0] for row in spreadsheet_rows(openst_step)) == ["Brain_Section_1", "Brain_Section_2"]

    columns = ["Sample Name", "Image"]
    instructions = "Download from https://example.org/openst (pw: openst)"
    wf.post("open-s-t-annotation", {
        **spreadsheet(columns, [["Brain_Section_1", "b1.tif"], ["Brain_Section_2", ""]]),
        "instructions": instructions,
    }, status=202)  # image is required
    wf.post("open-s-t-annotation", {
        **spreadsheet(columns, [["Brain_Section_1", "b1.tif"], ["Brain_Section_1", "b2.tif"]]),
        "instructions": instructions,
    }, status=202)  # duplicate sample
    wf.post("open-s-t-annotation", {
        **spreadsheet(columns, [["Brain_Section_1", "b1.tif"], ["Brain_Section_2", "b2.tif"]]),
        "instructions": instructions,
    }, next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == {f"Brain_Section_{i}_{L.OPENST.identifier}" for i in (1, 2)}
    for i in (1, 2):
        library = libraries[f"Brain_Section_{i}_{L.OPENST.identifier}"]
        assert library.type == L.OPENST
        assert library.genome_ref == C.GenomeRef.MOUSE
        assert library.properties == {"image": f"b{i}.tif"}
        assert linked_samples(library) == {f"Brain_Section_{i}": None}

    session.refresh(seq_request)
    assert any(instructions in c.text for c in seq_request.comments)
