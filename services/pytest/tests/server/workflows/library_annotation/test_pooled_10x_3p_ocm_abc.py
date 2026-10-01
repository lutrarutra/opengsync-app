"""LibraryAnnotationWorkflow: pooled libraries, 10X 3' GEX with on-chip multiplexing (OCM) and antibody capture."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, pool_mapping, libraries_by_name, linked_samples, spreadsheet, spreadsheet_rows,
    assert_features_only_on_abc_libraries,
)

L = C.LibraryType

def test_pooled_10x_3p_ocm_abc_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("10X 3' OCM + ABC pooled libraries")

    samples = ["OCM_1", "OCM_2", "OCM_3", "OCM_4"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)

    wf.service(
        C.ServiceType.TENX_SC_GEX_3PRIME,
        next_step="define-multiplexed-samples",
        additional_services__ocm_multiplexing="on",
        optional_assays__antibody_capture="on",
        optional_assays__antibody_capture_kit="TotalSeq-B",
    )
    ocm_step = wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"],
        [["OCM_1", "Chip_1"], ["OCM_2", "Chip_1"], ["OCM_3", "Chip_2"], ["OCM_4", "Chip_2"]],
    ), next_step="o-c-m-annotation")
    # One pre-filled row per sample, not per sample x library type.
    assert sorted(row[0] for row in spreadsheet_rows(ocm_step)) == samples

    ocm_columns = ["Sample Name", "Multiplexing Pool", "Barcode ID"]
    wf.post("o-c-m-annotation", spreadsheet(ocm_columns, [
        ["OCM_1", "Chip_1", "OB1"], ["OCM_2", "Chip_1", "OB1"],
        ["OCM_3", "Chip_2", "OB1"], ["OCM_4", "Chip_2", "OB2"],
    ]), status=202)  # duplicate barcode within a chip
    wf.post("o-c-m-annotation", spreadsheet(ocm_columns, [
        ["OCM_1", "Chip_1", "OB1"], ["OCM_2", "Chip_1", "OB5"],
        ["OCM_3", "Chip_2", "OB1"], ["OCM_4", "Chip_2", "OB2"],
    ]), status=202)  # only OB1-OB4 exist
    wf.post("o-c-m-annotation", spreadsheet(ocm_columns, [
        ["OCM_1", "Chip_1", "ob1"], ["OCM_2", "Chip_1", "OB-2"],
        ["OCM_3", "Chip_2", "1"], ["OCM_4", "Chip_2", "OB2"],
    ]), next_step="pooled-library-annotation")  # barcode ids are normalised to 'OB<n>'

    gex = L.TENX_SC_GEX_3PRIME.identifier
    abc = L.TENX_ANTIBODY_CAPTURE.identifier
    library_names = [f"{chip}_{t}" for chip in ["Chip_1", "Chip_2"] for t in [gex, abc]]
    wf.post("pooled-library-annotation", spreadsheet(
        ["Library Name", "Pool"], [[name, "OCM_Pool"] for name in library_names],
    ), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["OCM_Pool"]), next_step="barcode-input")

    sequences = {name: seq for name, seq in zip(library_names, ["ACGTACGT", "TGCATGCA", "GGAACCTT", "CCTTGGAA"])}
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [name, "", "", "", seq, "", "", "AGCTAGCT"] for name, seq in sequences.items()
    ]), next_step="barcode-match")
    wf.post("barcode-match", {
        "i7_kit": "0", "i7_option": "forward", "i7_primer": "AATGATACGGCGACCACCGA",
        "i5_kit": "0", "i5_option": "forward", "i5_primer": "CAAGCAGAAGACGGCATACGA",
    }, next_step="feature-annotation")

    wf.post("feature-annotation", spreadsheet(
        ["Sample Name", "Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"],
        [["", "", "", "CD3", "CTCATTGTAACTCCT", "5PNNNNNNNNNN(BC)", "R2"]],
    ), next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == set(library_names)
    ocm_barcodes = {"OCM_1": "OB1", "OCM_2": "OB2", "OCM_3": "OB1", "OCM_4": "OB2"}
    for name, library in libraries.items():
        assert library.mux_type == C.MUXType.TENX_ON_CHIP
        assert library.pool is not None and library.pool.name == "OCM_Pool"
        assert library.index_type == C.IndexType.DUAL_INDEX
        assert [(i.sequence_i7, i.sequence_i5) for i in library.indices] == [(sequences[name], "AGCTAGCT")]
        chip_samples = samples[:2] if name.startswith("Chip_1") else samples[2:]
        assert linked_samples(library) == {s: {"barcode": ocm_barcodes[s]} for s in chip_samples}

    for chip in ["Chip_1", "Chip_2"]:
        assert [f.name for f in libraries[f"{chip}_{abc}"].features] == ["CD3"]
    assert_features_only_on_abc_libraries(libraries)
