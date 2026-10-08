"""LibraryAnnotationWorkflow: index clashes are shown on the review step, not rejected.

As in legacy, barcode input does not check for clashes between libraries. The review step
(``complete-s-a-s``) runs ``check_indices`` per sequencing pool and flags identical
indices in its Barcodes tab; the submission still goes through and clashes are resolved
by the facility (see ``CheckBarcodeClashesAction``).
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


def _review(client, session: SyncSession, user, token: str, pools: dict[str, str], indices: dict[str, tuple[str, str]]):
    """Annotate one bulk RNA-seq library per sample; ``pools`` maps sample → pool."""
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
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [lib[s], "", "", "", indices[s][0], "", "", indices[s][1]] for s in samples
    ]), next_step="barcode-match")
    review = wf.post("barcode-match", {**CUSTOM_MATCH, "i5_kit": "0", "i5_option": "forward", "i5_primer": "CAAGCAGAAGACGGCATACGA"}, next_step="complete-s-a-s")
    return seq_request, wf, lib, review


def test_identical_indices_in_one_pool_are_flagged_on_review(client, session: SyncSession, user, user_token):
    seq_request, wf, lib, review = _review(
        client, session, user, user_token,
        pools={"Clash_A": "Pool_1", "Clash_B": "Pool_1"},
        indices={"Clash_A": (SAME_I7, SAME_I5), "Clash_B": (SAME_I7, SAME_I5)},
    )

    assert ERROR in review.text
    assert "text-danger" in review.text  # Barcodes tab is highlighted

    # Legacy parity: the clash does not block submission.
    wf.complete()
    libraries = libraries_by_name(session, seq_request.id)
    for name in lib.values():
        assert [(i.sequence_i7, i.sequence_i5) for i in libraries[name].indices] == [(SAME_I7, SAME_I5)]


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
