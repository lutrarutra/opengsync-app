"""LibraryAnnotationWorkflow: index clashes between libraries.

Libraries of one pool with the same index combination cannot be demultiplexed, so the barcode
input step rejects them (decided after the customer test 2026-11-04; legacy only flagged them on the
review step). Smaller distances are still only flagged on the review step (``complete-s-a-s``), which
runs ``check_indices`` per pool; the facility resolves those (see ``CheckBarcodeClashesAction``).
"""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, libraries_by_name, spreadsheet,
)

L = C.LibraryType
ERROR = "Hamming distance of 0 between barcode combination"
CUSTOM_MATCH = {"i7_kit": "0", "i7_option": "forward", "i7_primer": "AATGATACGGCGACCACCGA"}
SAME_I7, SAME_I5 = "ACGTACGTAC", "TGCATGCATG"
OTHER_I7, OTHER_I5 = "GGGGCCCCAA", "TTTTAAAAGG"


def _to_barcodes(client, session: SyncSession, user, token: str, pools: dict[str, str], indices: dict[str, tuple[str, str]], status: int = 200, next_step: str | None = "barcode-match"):
    """Annotate one bulk RNA-seq library per sample up to the barcode input; ``pools`` maps sample → pool."""
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()
    wf = AnnotationWorkflow(client, token, seq_request.id)
    wf.begin()
    wf.project("Barcode clash review")
    samples = list(pools)
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="pooled-library-annotation")
    lib = {s: f"{s}_{L.BULK_RNA_SEQ.identifier}" for s in samples}
    wf.post("pooled-library-annotation", spreadsheet(["Library Name", "Pool"], [[lib[s], pools[s]] for s in samples]), next_step="pool-mapping")
    pool_names = list(dict.fromkeys(pools.values()))
    data = {"contact_name": "Test Contact", "contact_email": "contact@example.com", "contact_phone": "123456"}
    for i, pool in enumerate(pool_names):
        data[f"pool_forms-{i}-raw_label"] = pool
        data[f"pool_forms-{i}-new_pool_name"] = pool
    wf.post("pool-mapping", data, next_step="barcode-input")
    response = wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [lib[s], "", "", "", indices[s][0], "", "", indices[s][1]] for s in samples
    ]), status=status, next_step=next_step)
    return seq_request, wf, lib, response


def _review(client, session: SyncSession, user, token: str, pools: dict[str, str], indices: dict[str, tuple[str, str]]):
    """Annotate up to the review step."""
    seq_request, wf, lib, _ = _to_barcodes(client, session, user, token, pools, indices)
    wf.post("barcode-match", {**CUSTOM_MATCH, "i5_kit": "0", "i5_option": "forward", "i5_primer": "CAAGCAGAAGACGGCATACGA"}, next_step="library-protocol-annotation")
    review = wf.protocols()
    return seq_request, wf, lib, review


def test_identical_indices_in_one_pool_are_rejected(client, session: SyncSession, user, user_token):
    _, wf, _, response = _to_barcodes(
        client, session, user, user_token,
        pools={"Clash_A": "Pool_1", "Clash_B": "Pool_1"},
        indices={"Clash_A": (SAME_I7, SAME_I5), "Clash_B": (SAME_I7, SAME_I5)},
        status=202, next_step="barcode-input",
    )
    assert "Same index combination as another library in pool &#39;Pool_1&#39;" in response.text or \
        "Same index combination as another library in pool 'Pool_1'" in response.text


def test_identical_indices_in_different_pools_are_not_a_clash(client, session: SyncSession, user, user_token):
    _, wf, _, review = _review(
        client, session, user, user_token,
        pools={"Clash_A": "Pool_1", "Clash_B": "Pool_2"},
        indices={"Clash_A": (SAME_I7, SAME_I5), "Clash_B": (SAME_I7, SAME_I5)},
    )

    assert ERROR not in review.text
    wf.complete()


def test_distinct_indices_have_no_clash(client, session: SyncSession, user, user_token):
    _, wf, _, review = _review(
        client, session, user, user_token,
        pools={"Clash_A": "Pool_1", "Clash_B": "Pool_1"},
        indices={"Clash_A": (SAME_I7, SAME_I5), "Clash_B": (OTHER_I7, OTHER_I5)},
    )

    assert ERROR not in review.text
    assert "text-danger" not in review.text
    wf.complete()


def test_review_shows_pool_names_not_labels(client, session: SyncSession, user, user_token):
    """The library sheet groups by a free label; the review shows the pool name given in the pool step."""
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()
    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Pool names on review")
    wf.samples([["Label_A", HUMAN]])
    wf.attributes(["Label_A"])
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="pooled-library-annotation")
    lib = f"Label_A_{L.BULK_RNA_SEQ.identifier}"
    wf.post("pooled-library-annotation", spreadsheet(["Library Name", "Pool"], [[lib, "my raw label"]]), next_step="pool-mapping")
    wf.post("pool-mapping", {
        "contact_name": "Test Contact", "contact_email": "contact@example.com", "contact_phone": "123456",
        "pool_forms-0-raw_label": "my raw label", "pool_forms-0-new_pool_name": "Resolved_Pool",
    }, next_step="barcode-input")
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [[lib, "", "", "", OTHER_I7, "", "", OTHER_I5]]), next_step="barcode-match")
    wf.post("barcode-match", {**CUSTOM_MATCH, "i5_kit": "0", "i5_option": "forward", "i5_primer": "CAAGCAGAAGACGGCATACGA"}, next_step="library-protocol-annotation")
    review = wf.protocols()

    assert "<td>Resolved_Pool</td>" in review.text
    assert "<td>my raw label</td>" not in review.text


def test_barcode_match_says_when_nothing_matched(client, session: SyncSession, user, user_token):
    _, _, _, response = _to_barcodes(
        client, session, user, user_token,
        pools={"Match_A": "Pool_1"}, indices={"Match_A": (OTHER_I7, OTHER_I5)},
    )
    assert "None of the sequences match a kit in the database" in response.text
    assert "some matches were found" not in response.text


def test_clash_error_names_the_pool_not_its_label(client, session: SyncSession, user, user_token):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()
    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Clash pool name")
    wf.samples([["Named_A", HUMAN], ["Named_B", HUMAN]])
    wf.attributes(["Named_A", "Named_B"])
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="pooled-library-annotation")
    libs = [f"Named_{s}_{L.BULK_RNA_SEQ.identifier}" for s in "AB"]
    wf.post("pooled-library-annotation", spreadsheet(["Library Name", "Pool"], [[lib, "raw label"] for lib in libs]), next_step="pool-mapping")
    wf.post("pool-mapping", {
        "contact_name": "Test Contact", "contact_email": "contact@example.com", "contact_phone": "123456",
        "pool_forms-0-raw_label": "raw label", "pool_forms-0-new_pool_name": "Named_Pool",
    }, next_step="barcode-input")
    response = wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [lib, "", "", "", SAME_I7, "", "", SAME_I5] for lib in libs
    ]), status=202, next_step="barcode-input")

    assert "pool &#39;Named_Pool&#39;" in response.text or "pool 'Named_Pool'" in response.text
