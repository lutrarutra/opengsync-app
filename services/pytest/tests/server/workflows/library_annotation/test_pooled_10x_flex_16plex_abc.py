"""LibraryAnnotationWorkflow: pooled libraries, 10X Flex 16-plex + Flex ABC, probe barcodes and kit-matched indices."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, create_dual_index_kit, pool_mapping,
    libraries_by_name, linked_samples, spreadsheet, spreadsheet_rows,
    assert_features_only_on_abc_libraries,
)

L = C.LibraryType


def test_pooled_10x_flex_16plex_abc_annotation(
    client, session: SyncSession, user, user_token,
):
    kit = create_dual_index_kit(session, "TT-SET-A", "Dual Index Kit TT Set A", {
        "A1": ("SI-TT-A1", "GTAACATGCG", "SI-TT-A1", "AGGTAACACT"),
        "A2": ("SI-TT-A2", "GTGGATCAAA", "SI-TT-A2", "CAGGGTTGGC"),
    })

    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("10X Flex 16-plex + ABC pooled libraries")

    samples = ["Flex_S1", "Flex_S2", "Flex_S3"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)

    wf.service(
        C.ServiceType.TENX_SC_16_PLEX_FLEX,
        next_step="define-multiplexed-samples",
        optional_assays__antibody_capture="on",
        optional_assays__antibody_capture_kit="TotalSeq-B Flex",
    )
    flex_step = wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"], [[s, "FlexPool"] for s in samples],
    ), next_step="flex-annotation")
    assert sorted(row[0] for row in spreadsheet_rows(flex_step)) == samples

    flex_columns = ["Sample Name", "Multiplexing Pool", "Barcode ID"]
    wf.post("flex-annotation", spreadsheet(flex_columns, [
        ["Flex_S1", "FlexPool", "BC001"], ["Flex_S2", "FlexPool", "BC001"], ["Flex_S3", "FlexPool", "BC003"],
    ]), status=202)  # duplicate probe barcode in a pool
    wf.post("flex-annotation", spreadsheet(flex_columns, [
        ["Flex_S1", "FlexPool", "BC001"], ["Flex_S2", "FlexPool", "BC002"], ["Flex_S3", "FlexPool", "BC017"],
    ]), status=202)  # 16-plex has BC001-BC016 only
    wf.post("flex-annotation", spreadsheet(flex_columns, [
        ["Flex_S1", "FlexPool", "1"], ["Flex_S2", "FlexPool", "BC02"], ["Flex_S3", "FlexPool", "bc003"],
    ]), next_step="pooled-library-annotation")  # normalised to BC001, BC002, BC003

    gex = f"FlexPool_{L.TENX_SC_GEX_FLEX.identifier}"
    abc = f"FlexPool_{L.TENX_SC_ABC_FLEX.identifier}"
    wf.post("pooled-library-annotation", spreadsheet(
        ["Library Name", "Pool"], [[gex, "Flex_Seq_Pool"], [abc, "Flex_Seq_Pool"]],
    ), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["Flex_Seq_Pool"]), next_step="barcode-input")

    # Sequences only: barcode-match then offers the kit they match.
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [gex, "", "", "", "GTAACATGCG", "", "", "AGGTAACACT"],
        [abc, "", "", "", "GTGGATCAAA", "", "", "CAGGGTTGGC"],
    ]), next_step="barcode-match")
    wf.post("barcode-match", {"i7_kit": str(kit.id), "i5_kit": str(kit.id)}, next_step="feature-annotation")

    wf.post("feature-annotation", spreadsheet(
        ["Sample Name", "Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"],
        [["FlexPool", "", "", "CD19", "CTGGGCAATTACTCG", "5PNNNNNNNNNN(BC)", "R2"]],
    ), next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == {gex, abc}
    for library in libraries.values():
        assert library.mux_type == C.MUXType.TENX_FLEX_PROBE
        assert library.pool is not None and library.pool.name == "Flex_Seq_Pool"
        assert library.index_type == C.IndexType.DUAL_INDEX
        assert len(library.indices) == 1
        index = library.indices[0]
        assert index.index_kit_i7_id == kit.id and index.index_kit_i5_id == kit.id
        assert index.orientation == C.BarcodeOrientation.FORWARD

    assert libraries[gex].indices[0].name_i7 == "SI-TT-A1"
    assert libraries[abc].indices[0].name_i7 == "SI-TT-A2"

    # GEX probes use BCxxx, the matching antibody barcodes ABxxx.
    assert linked_samples(libraries[gex]) == {"Flex_S1": {"barcode": "BC001"}, "Flex_S2": {"barcode": "BC002"}, "Flex_S3": {"barcode": "BC003"}}
    assert linked_samples(libraries[abc]) == {"Flex_S1": {"barcode": "AB001"}, "Flex_S2": {"barcode": "AB002"}, "Flex_S3": {"barcode": "AB003"}}

    assert [f.name for f in libraries[abc].features] == ["CD19"]
    assert_features_only_on_abc_libraries(libraries)
