"""LibraryAnnotationWorkflow: steps that do not apply, or are not reached yet, are rejected.

Every step has its own URL and the workflow state is only keyed by UUID, so a client can
post to any step directly. A step that does not apply to the annotation (e.g. pool
annotation for raw samples), or one that comes later than the current step, must give a
controlled 4xx and leave the annotation unchanged — not a 500 from missing state, and
not silently re-routing the workflow.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, BARCODE_COLUMNS, HUMAN, libraries_by_name, pool_mapping, spreadsheet

L = C.LibraryType


def _lenient(wf: AnnotationWorkflow) -> AnnotationWorkflow:
    """Same workflow, but server errors come back as 500 responses instead of raising."""
    wf.client = TestClient(wf.client.app, raise_server_exceptions=False)
    return wf


def _raw_bulk_at_review(client, session: SyncSession, user, token: str):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    wf = AnnotationWorkflow(client, token, seq_request.id)
    wf.begin()
    wf.project("Step order raw bulk")
    wf.samples([["Order_1", HUMAN]])
    wf.attributes(["Order_1"])
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="complete-s-a-s")
    return seq_request, wf


def _assert_rejected(response) -> None:
    assert 400 <= response.status_code < 500, f"expected a 4xx, got {response.status_code}"


def test_pool_annotation_for_raw_samples_is_rejected(client, session: SyncSession, user, user_token):
    seq_request, wf = _raw_bulk_at_review(client, session, user, user_token)
    lib = f"Order_1_{L.BULK_RNA_SEQ.identifier}"

    _assert_rejected(_lenient(wf).post("pooled-library-annotation", spreadsheet(
        ["Library Name", "Pool"], [[lib, "Sneaky_Pool"]],
    ), status=None))
    _assert_rejected(wf.post("pool-mapping", pool_mapping(["Sneaky_Pool"]), status=None))

    wf.client = client
    wf.complete()
    library = libraries_by_name(session, seq_request.id)[lib]
    assert library.pool_id is None
    assert session.count(Q.pool.select(seq_request_id=seq_request.id)) == 0


def test_barcode_input_for_raw_samples_is_rejected(client, session: SyncSession, user, user_token):
    seq_request, wf = _raw_bulk_at_review(client, session, user, user_token)
    lib = f"Order_1_{L.BULK_RNA_SEQ.identifier}"

    _assert_rejected(_lenient(wf).post("barcode-input", spreadsheet(
        BARCODE_COLUMNS, [[lib, "", "", "", "ACGTACGTAC", "", "", ""]],
    ), status=None))

    wf.client = client
    wf.complete()
    assert libraries_by_name(session, seq_request.id)[lib].indices == []


def test_previous_of_a_step_never_reached_is_rejected(client, session: SyncSession, user, user_token):
    _, wf = _raw_bulk_at_review(client, session, user, user_token)
    _lenient(wf)

    for step in ("pooled-library-annotation", "barcode-input", "feature-annotation"):
        _assert_rejected(wf.client.get(
            f"{wf.prefix}/{step}", params=wf.params, cookies={"access_token": wf.token},
        ))


def test_skipping_ahead_to_completion_is_rejected(client, session: SyncSession, user, user_token):
    """Posting the final step right after project selection creates nothing."""
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    wf = _lenient(AnnotationWorkflow(client, user_token, seq_request.id))
    wf.begin()
    wf.project("Skip ahead project")

    _assert_rejected(wf.post("complete-s-a-s", status=None))

    session.expire_all()
    assert session.first(Q.project.select(title="Skip ahead project")) is None
    assert session.count(Q.library.select(seq_request_id=seq_request.id)) == 0


def test_skipping_ahead_to_service_selection_is_rejected(client, session: SyncSession, user, user_token):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    wf = _lenient(AnnotationWorkflow(client, user_token, seq_request.id))
    wf.begin()
    wf.project("Skip ahead to service")

    _assert_rejected(wf.post("select-service", {"service_type": str(C.ServiceType.BULK_RNA_SEQ.id)}, status=None))
