"""LibraryAnnotationWorkflow: pooled libraries, 10X 3' GEX with CMO multiplexing resolved from a feature kit."""

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, pool_mapping,
    libraries_by_name, linked_samples, spreadsheet, spreadsheet_rows,
)

L = C.LibraryType

CMOS = {
    "CMO301": "ATGAGGAATTCCTGC",
    "CMO302": "CATGCCAATAGAGCG",
    "CMO303": "CCGTCGTCCAAGCAT",
}
PATTERN = "5PNNNNNNNNNN(BC)"


def test_pooled_10x_3p_oligo_mux_kit_annotation(
    client, session: SyncSession, user, user_token,
):
    kit = session.save(Q.feature_kit.create(name="3' CellPlex Kit Set A", identifier="CMO-SET-A", type=C.FeatureType.CMO), flush=True)
    for name, sequence in CMOS.items():
        session.save(Q.feature.create(
            identifier=None, name=name, sequence=sequence, pattern=PATTERN, read="R2",
            type=C.FeatureType.CMO, feature_kit_id=kit.id,
        ), flush=True)
    session.commit()

    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("10X 3' CMO kit pooled libraries")
    samples = ["CMO_S1", "CMO_S2", "CMO_S3"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)
    wf.service(
        C.ServiceType.TENX_SC_GEX_3PRIME, next_step="define-multiplexed-samples",
        additional_services__oligo_multiplexing="on",
        additional_services__oligo_multiplexing_kit="3' CellPlex Kit Set A",
    )
    oligo_step = wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"], [[s, "CMO_Pool"] for s in samples],
    ), next_step="oligo-mux-annotation")
    assert sorted(row[0] for row in spreadsheet_rows(oligo_step)) == samples
    assert "[CMO-SET-A]" in oligo_step.text  # CMO kits are offered in the Kit dropdown

    kit_label = "[CMO-SET-A] 3' CellPlex Kit Set A"
    oligo_columns = ["Sample Name", "Multiplexing Pool", "Kit", "Feature", "Sequence", "Pattern", "Read"]
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, [
        ["CMO_S1", "CMO_Pool", kit_label, "CMO301", "", "", ""],
        ["CMO_S2", "CMO_Pool", kit_label, "CMO399", "", "", ""],
        ["CMO_S3", "CMO_Pool", kit_label, "CMO303", "", "", ""],
    ]), status=202)  # feature not in kit
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, [
        ["CMO_S1", "CMO_Pool", kit_label, "CMO301", "", "", ""],
        ["CMO_S2", "CMO_Pool", kit_label, "CMO301", "", "", ""],
        ["CMO_S3", "CMO_Pool", kit_label, "CMO303", "", "", ""],
    ]), status=202)  # same CMO twice in a pool
    valid_oligo_rows = [
        ["CMO_S1", "CMO_Pool", kit_label, "CMO301", "", "", ""],
        ["CMO_S2", "CMO_Pool", kit_label, "CMO302", "", "", ""],
        ["CMO_S3", "CMO_Pool", "", "", "TTGCTCGCAAGGTAG", PATTERN, "R2"],  # custom oligo next to kit ones
    ]
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, valid_oligo_rows), next_step="pooled-library-annotation")

    # 'Back' shows the oligos as they were entered.
    back = wf.back("oligo-mux-annotation")
    assert [[cell or "" for cell in row[:7]] for row in spreadsheet_rows(back)] == valid_oligo_rows
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, valid_oligo_rows), next_step="pooled-library-annotation")

    gex = f"CMO_Pool_{L.TENX_SC_GEX_3PRIME.identifier}"
    mux = f"CMO_Pool_{L.TENX_MUX_OLIGO.identifier}"
    wf.post("pooled-library-annotation", spreadsheet(
        ["Library Name", "Pool"], [[gex, "Seq_Pool_1"], [mux, "Seq_Pool_1"]],
    ), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["Seq_Pool_1"]), next_step="barcode-input")
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [gex, "", "", "", "ACGTACGTAC", "", "", "TGCATGCATG"],
    ]), status=202)  # the multiplexing-capture library needs an index too
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [gex, "", "", "", "ACGTACGTAC", "", "", "TGCATGCATG"],
        [mux, "", "", "", "GGTTCCAAGG", "", "", "CCAAGGTTCC"],
    ]), next_step="barcode-match")
    wf.post("barcode-match", {
        "i7_kit": "0", "i7_option": "forward", "i7_primer": "AATGATACGGCGACCACCGA",
        "i5_kit": "0", "i5_option": "forward", "i5_primer": "CAAGCAGAAGACGGCATACGA",
    }, next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == {gex, mux}
    expected_mux = {
        "CMO_S1": {"barcode": CMOS["CMO301"], "pattern": PATTERN, "read": "R2"},
        "CMO_S2": {"barcode": CMOS["CMO302"], "pattern": PATTERN, "read": "R2"},
        "CMO_S3": {"barcode": "TTGCTCGCAAGGTAG", "pattern": PATTERN, "read": "R2"},
    }
    for library in libraries.values():
        assert library.mux_type == C.MUXType.TENX_OLIGO
        assert library.pool is not None and library.pool.name == "Seq_Pool_1"
        assert library.index_type == C.IndexType.DUAL_INDEX
        assert linked_samples(library) == expected_mux
