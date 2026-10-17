"""LibraryAnnotationWorkflow: index (barcode) input is validated and normalised before it is stored."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, create_dual_index_kit, pool_mapping,
    libraries_by_name, spreadsheet,
)

L = C.LibraryType
KIT = "[TT-SET-A] Dual Index Kit TT Set A"


def test_input_index_barcodes(
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
    wf.project("Index input validation")
    samples = ["Idx_1", "Idx_2", "Idx_3"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="pooled-library-annotation")
    lib = {s: f"{s}_{L.BULK_RNA_SEQ.identifier}" for s in samples}
    wf.post("pooled-library-annotation", spreadsheet(["Library Name", "Pool"], [[name, "Idx_Pool"] for name in lib.values()]), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["Idx_Pool"]), next_step="barcode-input")

    valid = {
        "Idx_1": [lib["Idx_1"], "A01", KIT, "", "", "", "", ""],  # kit + well ('A01' == 'A1')
        "Idx_2": [lib["Idx_2"], "", KIT, "SI-TT-A2", "", "", "", ""],  # kit + barcode name
        "Idx_3": [lib["Idx_3"], "", "", "", " acgt-acgt ac ", "", "", "tgca tgca tg"],  # custom, messy
    }

    def rows(**overrides: list[str]) -> list[list[str]]:
        return [overrides.get(s, valid[s]) for s in samples]

    invalid = [
        (rows(Idx_3=[lib["Idx_3"], "", "", "", "ACGTXCGTAC", "", "", ""]), "non-DNA base in i7"),
        (rows(Idx_3=[lib["Idx_3"], "", "", "", "ACGTACGTAC", "", "", "TGCA!?ZZTG"]), "non-DNA base in i5"),
        (rows(Idx_3=[lib["Idx_3"], "", "", "", "A" * 40, "", "", ""]), "i7 longer than the column"),
        (rows(Idx_3=[lib["Idx_3"], "", "", "", "", "", "", "TGCATGCATG"]), "i5 without i7"),
        (rows(Idx_1=[lib["Idx_1"], "H12", KIT, "", "", "", "", ""]), "well not in kit"),
        (rows(Idx_2=[lib["Idx_2"], "", KIT, "SI-TT-Z9", "", "", "", ""]), "barcode name not in kit"),
        (rows(Idx_1=[lib["Idx_1"], "", KIT, "", "", "", "", ""]), "kit without well or name"),
        (rows(Idx_1=[lib["Idx_1"], "A1", "[NOPE] Unknown kit", "", "", "", "", ""]), "unknown kit"),
        (rows(Idx_1=["Not_A_Library", "A1", KIT, "", "", "", "", ""]), "unknown library"),
        (rows()[:2], "library without index"),
    ]
    for payload, reason in invalid:
        response = wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, payload), status=202)
        assert wf.rendered_step(response) == "barcode-input", reason

    # Kit indices are complete, the custom one has no kit: no matching step is needed.
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, rows()), next_step="complete-s-a-s")
    wf.complete()

    libraries = libraries_by_name(session, seq_request.id)
    idx_1, idx_2, idx_3 = (libraries[lib[s]].indices for s in samples)
    assert [(i.name_i7, i.sequence_i7, i.name_i5, i.sequence_i5) for i in idx_1] == [("SI-TT-A1", "GTAACATGCG", "SI-TT-A1", "AGGTAACACT")]
    assert [(i.name_i7, i.sequence_i7, i.name_i5, i.sequence_i5) for i in idx_2] == [("SI-TT-A2", "GTGGATCAAA", "SI-TT-A2", "CAGGGTTGGC")]
    for index in idx_1 + idx_2:
        assert index.index_kit_i7_id == kit.id and index.index_kit_i5_id == kit.id
        assert index.orientation == C.BarcodeOrientation.FORWARD
    assert [(i.sequence_i7, i.sequence_i5) for i in idx_3] == [("ACGTACGTAC", "TGCATGCATG")]
    assert idx_3[0].index_kit_i7_id is None
    for s in samples:
        assert libraries[lib[s]].index_type == C.IndexType.DUAL_INDEX
