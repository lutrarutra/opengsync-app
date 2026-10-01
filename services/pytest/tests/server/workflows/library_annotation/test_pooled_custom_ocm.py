"""LibraryAnnotationWorkflow: pooled libraries, custom service with on-chip multiplexing (OCM)."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, pool_mapping,
    libraries_by_name, linked_samples, spreadsheet,
)

L = C.LibraryType
LABEL = dict(C.LibraryType.as_selectable())


def test_pooled_custom_ocm_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Custom + OCM pooled libraries")
    samples = ["Chip_S1", "Chip_S2"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)
    wf.service(C.ServiceType.CUSTOM, next_step="define-multiplexed-samples", additional_services__ocm_multiplexing="on")

    custom_step = wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"], [[s, "OCM_Chip"] for s in samples],
    ), next_step="custom-assay-annotation")
    assert wf.back_step(custom_step) == "define-multiplexed-samples"

    wf.post("custom-assay-annotation", spreadsheet(["Sample Name (Pool)", "Library Type"], [
        ["OCM_Chip", LABEL[L.TENX_SC_GEX_3PRIME.id]],
        ["OCM_Chip", LABEL[L.TENX_ANTIBODY_CAPTURE.id]],
    ]), next_step="o-c-m-annotation")
    wf.post("o-c-m-annotation", spreadsheet(["Sample Name", "Multiplexing Pool", "Barcode ID"], [
        ["Chip_S1", "OCM_Chip", "OB1"], ["Chip_S2", "OCM_Chip", "OB2"],
    ]), next_step="pooled-library-annotation")

    gex = f"OCM_Chip_{L.TENX_SC_GEX_3PRIME.identifier}"
    abc = f"OCM_Chip_{L.TENX_ANTIBODY_CAPTURE.identifier}"
    wf.post("pooled-library-annotation", spreadsheet(
        ["Library Name", "Pool"], [[gex, "Custom_Pool"], [abc, "Custom_Pool"]],
    ), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["Custom_Pool"]), next_step="barcode-input")
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [gex, "", "", "", "ACGTACGTAC", "", "", ""],
        [abc, "", "", "", "TTGGCCAATT", "", "", ""],
    ]), next_step="barcode-match")
    wf.post("barcode-match", {"i7_kit": "0", "i7_option": "forward", "i7_primer": "AATGATACGGCGACCACCGA"}, next_step="feature-annotation")
    wf.post("feature-annotation", spreadsheet(
        ["Sample Name", "Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"],
        [["OCM_Chip", "", "", "CD3", "CTCATTGTAACTCCT", "5PNNNNNNNNNN(BC)", "R2"]],
    ), next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == {gex, abc}
    for library in libraries.values():
        assert library.service_type == C.ServiceType.CUSTOM
        assert library.mux_type == C.MUXType.TENX_ON_CHIP
        assert library.pool is not None and library.pool.name == "Custom_Pool"
        assert linked_samples(library) == {"Chip_S1": {"barcode": "OB1"}, "Chip_S2": {"barcode": "OB2"}}
    assert [f.name for f in libraries[abc].features] == ["CD3"]
    assert libraries[gex].features == []  # sample-specific feature row
