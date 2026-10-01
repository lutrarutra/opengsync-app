"""LibraryAnnotationWorkflow: raw samples, custom service with 10X Visium + antibody capture (spatial protein)."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, libraries_by_name, linked_samples, spreadsheet,
    assert_features_only_on_abc_libraries,
)

L = C.LibraryType
LABEL = dict(C.LibraryType.as_selectable())


def test_raw_custom_visium_abc_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Visium + ABC custom raw samples")
    wf.samples([["Section_1", HUMAN], ["Section_2", HUMAN]])
    wf.attributes(["Section_1", "Section_2"])
    wf.service(C.ServiceType.CUSTOM, next_step="custom-assay-annotation")

    wf.post("custom-assay-annotation", spreadsheet(["Sample Name (Pool)", "Library Type"], [
        ["Section_1", LABEL[L.TENX_VISIUM_FFPE.id]],
        ["Section_1", LABEL[L.TENX_ANTIBODY_CAPTURE.id]],
        ["Section_2", LABEL[L.TENX_VISIUM_FFPE.id]],
    ]), next_step="feature-annotation")

    wf.post("feature-annotation", spreadsheet(
        ["Sample Name", "Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"],
        [["Section_1", "", "", "PanCK", "AAGCGTAATGCGTCA", "5PNNNNNNNNNN(BC)", "R2"]],
    ), next_step="visium-annotation")

    visium_columns = ["Sample Name", "Image", "Slide", "Area", "H&E Image"]
    instructions = "Images are on the shared drive: //share/visium/run42 (pw: visium)"
    wf.post("visium-annotation", {
        **spreadsheet(visium_columns, [
            ["Section_1", "s1.tif", "V11J26-127", "A1", ""],
            ["Section_1", "s1b.tif", "V11J26-127", "B1", ""],
            ["Section_2", "s2.tif", "V11J26-127", "C1", "s2_he.tif"],
        ]),
        "instructions": instructions,
    }, status=202)  # one Visium entry per sample
    wf.post("visium-annotation", {
        **spreadsheet(visium_columns, [
            ["Section_1", "s1.tif", "", "A1", ""],
            ["Section_2", "s2.tif", "V11J26-127", "C1", "s2_he.tif"],
        ]),
        "instructions": instructions,
    }, status=202)  # slide is required
    wf.post("visium-annotation", spreadsheet(visium_columns, [
        ["Section_1", "s1.tif", "V11J26-127", "A1", ""],
        ["Section_2", "s2.tif", "V11J26-127", "C1", "s2_he.tif"],
    ]), status=202)  # download instructions are required
    wf.post("visium-annotation", {
        **spreadsheet(visium_columns, [
            ["Section_1", "s1.tif", "V11J26-127", "A1", ""],
            ["Section_2", "s2.tif", "V11J26-127", "C1", "s2_he.tif"],
        ]),
        "instructions": instructions,
    }, next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    visium_1 = f"Section_1_{L.TENX_VISIUM_FFPE.identifier}"
    abc_1 = f"Section_1_{L.TENX_ANTIBODY_CAPTURE.identifier}"
    visium_2 = f"Section_2_{L.TENX_VISIUM_FFPE.identifier}"
    assert set(libraries) == {visium_1, abc_1, visium_2}
    assert linked_samples(libraries[visium_1]) == {"Section_1": None}
    assert linked_samples(libraries[abc_1]) == {"Section_1": None}

    assert libraries[visium_1].properties == {"image": "s1.tif", "slide": "V11J26-127", "area": "A1"}
    assert libraries[visium_2].properties == {"image": "s2.tif", "slide": "V11J26-127", "area": "C1", "he_image": "s2_he.tif"}
    assert not libraries[abc_1].properties
    assert [f.name for f in libraries[abc_1].features] == ["PanCK"]

    session.refresh(seq_request)
    assert any(instructions in c.text for c in seq_request.comments)
    assert_features_only_on_abc_libraries(libraries)
