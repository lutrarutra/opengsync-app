import pytest

from opengsync_db import SyncSession
from opengsync_db.categories import LibraryStatus as LB, SeqRequestStatus as RQ, SubmissionType
from opengsync_db.transitions import routes
from opengsync_db.transitions.rules import Snapshot

from ..create_units import create_user, create_seq_request, create_library


@pytest.mark.parametrize("submission_type, route_id", [
    (SubmissionType.RAW_SAMPLES, "raw_samples"),
    (SubmissionType.POOLED_LIBRARIES, "pooled_libraries"),
    (SubmissionType.UNPOOLED_LIBRARIES, "unpooled_libraries"),
    (SubmissionType.QC_ONLY, "qc_only"),
])
def test_route_by_submission_type(session: SyncSession, submission_type: SubmissionType, route_id: str):
    seq_request = create_seq_request(session, create_user(session), submission_type=submission_type)
    assert routes.infer_route(session, seq_request).id == route_id


def _reseq_request(session: SyncSession, clone_status: LB = LB.ACCEPTED):
    user = create_user(session)
    seq_request = create_seq_request(session, user, submission_type=SubmissionType.RAW_SAMPLES)
    original = create_library(session, user, seq_request)
    original.status = LB.SEQUENCED
    clone = create_library(session, user, seq_request)
    clone.status = clone_status
    clone.original_library_id = original.id
    session.save(original)
    session.save(clone, flush=True)
    return seq_request


def test_reseq_route_inferred(session: SyncSession):
    assert routes.infer_route(session, _reseq_request(session)).id == "reseq"


def test_reseq_route_not_inferred_when_clone_is_done(session: SyncSession):
    assert routes.infer_route(session, _reseq_request(session, clone_status=LB.SEQUENCED)).id == "raw_samples"


def test_reseq_not_inferred_without_sequenced_libraries(session: SyncSession):
    # a cloned request: libraries have an original, but nothing in it is sequenced yet
    user = create_user(session)
    seq_request = create_seq_request(session, user, submission_type=SubmissionType.RAW_SAMPLES)
    original = create_library(session, user, create_seq_request(session, user))
    clone = create_library(session, user, seq_request)
    clone.status = LB.ACCEPTED
    clone.original_library_id = original.id
    session.save(clone, flush=True)
    assert routes.infer_route(session, seq_request).id == "raw_samples"


def test_override_wins(session: SyncSession):
    seq_request = _reseq_request(session)
    seq_request.route_override = "pooled_libraries"  # column added with status history; plain attribute until then
    assert routes.infer_route(session, seq_request).id == "pooled_libraries"


def test_unknown_override_is_ignored(session: SyncSession):
    seq_request = create_seq_request(session, create_user(session), submission_type=SubmissionType.QC_ONLY)
    seq_request.route_override = "nope"
    assert routes.infer_route(session, seq_request).id == "qc_only"


def test_raw_samples_steps_progress(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user, submission_type=SubmissionType.RAW_SAMPLES)
    library = create_library(session, user, seq_request)
    library.status = LB.ACCEPTED
    seq_request.status = RQ.SAMPLES_RECEIVED
    session.save(library)
    session.save(seq_request, flush=True)

    snapshot = Snapshot(session)
    done = {step.id: step.done_when.evaluate(snapshot, seq_request).holds for step in routes.RAW_SAMPLES.steps}
    assert done["submit"] and done["review"] and done["receive"]
    assert not done["prep"] and not done["pool"] and not done["sequence"] and not done["finish"]


def test_rejected_request_has_not_passed_review(session: SyncSession):
    seq_request = create_seq_request(session, create_user(session), submission_type=SubmissionType.RAW_SAMPLES)
    seq_request.status = RQ.REJECTED
    session.save(seq_request, flush=True)
    assert not routes.REVIEW.done_when.evaluate(Snapshot(session), seq_request).holds
