"""LibraryAnnotationWorkflow: pooled libraries, Parse Biosciences WT with well multiplexing and Evercode TCR."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, pool_mapping,
    libraries_by_name, linked_samples, spreadsheet, spreadsheet_rows,
)

L = C.LibraryType


def test_pooled_parse_mux_tcr_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Parse WT mux + TCR pooled libraries")

    samples = ["PBMC_1", "PBMC_2", "PBMC_3", "PBMC_4"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)
    wf.service(
        C.ServiceType.PARSE,
        next_step="define-multiplexed-samples",
        optional_assays__parse_kit="1",  # WT_mini
        optional_assays__parse_chemistry="3",
        optional_assays__parse_mux="on",
        optional_assays__parse_tcr="on",
    )
    wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"],
        [["PBMC_1", "Sublib_1"], ["PBMC_2", "Sublib_1"], ["PBMC_3", "Sublib_2"], ["PBMC_4", "Sublib_2"]],
    ), next_step="parse-mux-annotation")

    well_columns = ["Sample Name", "Multiplexing Pool", "Well"]
    wf.post("parse-mux-annotation", spreadsheet(well_columns, [
        ["PBMC_1", "Sublib_1", "A1"], ["PBMC_2", "Sublib_1", "A1"],
        ["PBMC_3", "Sublib_2", "A1"], ["PBMC_4", "Sublib_2", "A2"],
    ]), status=202)  # same well twice in a sub-library
    wf.post("parse-mux-annotation", spreadsheet(well_columns, [
        ["PBMC_1", "Sublib_1", "a1"], ["PBMC_2", "Sublib_1", "A2"],
        ["PBMC_3", "Sublib_2", "A1"], ["PBMC_4", "Sublib_2", " b3 "],
    ]), next_step="pooled-library-annotation")  # wells are upper-cased and stripped

    gex, tcr = L.PARSE_SC_GEX.identifier, L.PARSE_EVERCODE_TCR.identifier
    library_names = [f"{sub}_{t}" for sub in ["Sublib_1", "Sublib_2"] for t in [gex, tcr]]

    # Going back keeps the annotated wells.
    back = wf.back("parse-mux-annotation")
    assert {row[0]: row[2] for row in spreadsheet_rows(back)} == {"PBMC_1": "A1", "PBMC_2": "A2", "PBMC_3": "A1", "PBMC_4": "B3"}
    wf.post("parse-mux-annotation", spreadsheet(well_columns, [
        ["PBMC_1", "Sublib_1", "A1"], ["PBMC_2", "Sublib_1", "A2"],
        ["PBMC_3", "Sublib_2", "A1"], ["PBMC_4", "Sublib_2", "B3"],
    ]), next_step="pooled-library-annotation")

    wf.post("pooled-library-annotation", spreadsheet(
        ["Library Name", "Pool"], [[name, "Parse_Pool"] for name in library_names],
    ), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["Parse_Pool"]), next_step="barcode-input")
    i7 = {name: seq for name, seq in zip(library_names, ["ACGTACGT", "TGCATGCA", "GGAACCTT", "CCTTGGAA"])}
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [name, "", "", "", seq, "", "", ""] for name, seq in i7.items()
    ]), next_step="barcode-match")
    wf.post("barcode-match", {"i7_kit": "0", "i7_option": "rc", "i7_primer": "AATGATACGGCGACCACCGA"}, next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == set(library_names)
    wells = {"PBMC_1": "A1", "PBMC_2": "A2", "PBMC_3": "A1", "PBMC_4": "B3"}
    for name, library in libraries.items():
        assert library.mux_type == C.MUXType.PARSE_WELLS
        assert library.index_type == C.IndexType.SINGLE_INDEX_I7
        assert library.pool is not None and library.pool.name == "Parse_Pool"
        sub_samples = samples[:2] if name.startswith("Sublib_1") else samples[2:]
        assert linked_samples(library) == {s: {"barcode": wells[s]} for s in sub_samples}
        # 'rc' stores the reverse complement of the entered i7 sequence
        index = library.indices[0]
        assert index.sequence_i7 == {"ACGTACGT": "ACGTACGT", "TGCATGCA": "TGCATGCA", "GGAACCTT": "AAGGTTCC", "CCTTGGAA": "TTCCAAGG"}[i7[name]]
        assert index.orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED
