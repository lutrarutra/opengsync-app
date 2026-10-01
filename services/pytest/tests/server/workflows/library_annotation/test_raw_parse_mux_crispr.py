"""LibraryAnnotationWorkflow: raw samples, Parse Biosciences WT with well multiplexing and CRISPR detect."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, libraries_by_name, linked_samples, spreadsheet

L = C.LibraryType


def test_raw_parse_mux_crispr_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Parse WT mux + CRISPR raw samples")

    samples = ["Parse_1", "Parse_2", "Parse_3"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)

    wf.service(C.ServiceType.PARSE, status=202, optional_assays__parse_mux="on")  # kit and chemistry are required
    wf.service(
        C.ServiceType.PARSE, status=202,
        optional_assays__parse_kit="2", optional_assays__parse_chemistry="3",
        optional_assays__parse_mux="on",
        additional_services__oligo_multiplexing="on",
        additional_services__oligo_multiplexing_kit="CMO",
    )  # Parse multiplexing cannot be combined with another multiplexing method
    define_step = wf.service(
        C.ServiceType.PARSE,
        next_step="define-multiplexed-samples",
        optional_assays__parse_kit="2",  # WT
        optional_assays__parse_chemistry="3",  # v3
        optional_assays__parse_mux="on",
        optional_assays__parse_crispr="on",
    )

    assert wf.back_step(define_step) == "select-service"

    wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"], [[s, "Sublib_1"] for s in samples],
    ), next_step="parse-c-r-i-s-p-r-guide-annotation")

    guide_columns = ["Guide Name", "Target Gene", "Prefix", "Guide Sequence", "Suffix"]
    prefix, suffix = "GTGGAAAGGACGAAACACCG", "GTTTTAGAGCTAGAAATAGCAAG"
    wf.post("parse-c-r-i-s-p-r-guide-annotation", spreadsheet(guide_columns, [
        ["sgTP53_1", "TP53", prefix, "CCATTGTTCAATATCGTCCG", suffix],
        ["sgTP53_1", "TP53", prefix, "GACGGAAACCGTAGCTGCCC", suffix],
    ]), status=202)  # guide names must be unique
    wf.post("parse-c-r-i-s-p-r-guide-annotation", spreadsheet(guide_columns, [
        ["sgTP53_1", "TP53", prefix, "", suffix],
    ]), status=202)  # guide sequence is required
    wf.post("parse-c-r-i-s-p-r-guide-annotation", spreadsheet(guide_columns, [
        ["sgTP53_1", "TP53", prefix, "CCATTGTTCAATATCGTCCG", suffix],
        ["sgNT_1", "Non-Targeting", prefix, "GACGGAAACCGTAGCTGCCC", suffix],
    ]), next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    gex = f"Sublib_1_{L.PARSE_SC_GEX.identifier}"
    crispr = f"Sublib_1_{L.PARSE_SC_CRISPR.identifier}"
    assert set(libraries) == {gex, crispr}
    for library in libraries.values():
        assert library.mux_type == C.MUXType.PARSE_WELLS
        assert library.service_type == C.ServiceType.PARSE
        assert linked_samples(library) == {s: {"barcode": None} for s in samples}

    guides = libraries[crispr].properties["crispr_guides"]
    assert [(g["guide_name"], g["target_gene"], g["guide_sequence"]) for g in guides] == [
        ("sgTP53_1", "TP53", "CCATTGTTCAATATCGTCCG"),
        ("sgNT_1", "Non-Targeting", "GACGGAAACCGTAGCTGCCC"),
    ]
    assert not (libraries[gex].properties or {}).get("crispr_guides")

    session.refresh(seq_request)
    comments = [c.text for c in seq_request.comments]
    assert "Parse Kit: WT" in comments
    assert "Parse Chemistry: v3" in comments
