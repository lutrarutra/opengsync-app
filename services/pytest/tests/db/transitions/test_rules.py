from opengsync_db import SyncSession, actions
from opengsync_db.categories import LibraryStatus as LB, SampleStatus as SA, SeqRequestStatus as RQ, SubmissionType
from opengsync_db.transitions import at_least, below, registry
from opengsync_db.transitions import relations as R
from opengsync_db.transitions.rules import (
    All, AnyOf, ChildrenAll, ChildrenAny, ChildrenNone, Not, Predicate, Snapshot, StatusIn, SubmissionTypeIn,
    BLOCKER_SAMPLE_SIZE,
)

from ..create_units import create_user, create_project, create_seq_request, create_library, create_sample


def _request_with_libraries(session: SyncSession, *statuses: LB, submission_type=SubmissionType.RAW_SAMPLES):
    user = create_user(session)
    seq_request = create_seq_request(session, user, submission_type=submission_type)
    libraries = []
    for status in statuses:
        library = create_library(session, user, seq_request)
        library.status = status
        session.save(library, flush=True)
        libraries.append(library)
    return user, seq_request, libraries


def test_status_in(session: SyncSession):
    _, seq_request, _ = _request_with_libraries(session)
    snapshot = Snapshot(session)
    assert StatusIn(frozenset([RQ.DRAFT])).evaluate(snapshot, seq_request).holds
    verdict = StatusIn(frozenset([RQ.ACCEPTED])).evaluate(snapshot, seq_request)
    assert not verdict.holds
    assert verdict.blockers[0].text == "status is DRAFT, needs ACCEPTED"


def test_submission_type_in(session: SyncSession):
    _, seq_request, _ = _request_with_libraries(session, submission_type=SubmissionType.POOLED_LIBRARIES)
    snapshot = Snapshot(session)
    assert SubmissionTypeIn(SubmissionType.POOLED_LIBRARIES).evaluate(snapshot, seq_request).holds
    assert not SubmissionTypeIn(SubmissionType.RAW_SAMPLES).evaluate(snapshot, seq_request).holds


def test_children_all_with_blockers(session: SyncSession):
    _, seq_request, libraries = _request_with_libraries(session, LB.POOLED, LB.ACCEPTED, LB.STORED, LB.FAILED)
    verdict = ChildrenAll(R.REQUEST_LIBRARIES, at_least(LB.POOLED)).evaluate(Snapshot(session), seq_request)
    assert not verdict.holds
    blocker = verdict.blockers[0]
    # FAILED (id 10) counts as beyond POOLED, like the legacy id comparison
    assert blocker.count == 2
    assert blocker.statuses == frozenset([LB.ACCEPTED, LB.STORED])
    assert set(blocker.sample_ids) == {libraries[1].id, libraries[2].id}
    assert blocker.text == "2 libraries of the request below POOLED (1 ACCEPTED, 1 STORED)"


def test_children_all_holds_and_nonempty(session: SyncSession):
    _, seq_request, _ = _request_with_libraries(session, LB.POOLED, LB.SEQUENCED)
    snapshot = Snapshot(session)
    assert ChildrenAll(R.REQUEST_LIBRARIES, at_least(LB.POOLED)).evaluate(snapshot, seq_request).holds

    _, empty_request, _ = _request_with_libraries(session)
    assert ChildrenAll(R.REQUEST_LIBRARIES, at_least(LB.POOLED)).evaluate(snapshot, empty_request).holds
    verdict = ChildrenAll(R.REQUEST_LIBRARIES, at_least(LB.POOLED), nonempty=True).evaluate(snapshot, empty_request)
    assert not verdict.holds
    assert verdict.blockers[0].text == "no libraries of the request"


def test_children_all_ignores_null_status(session: SyncSession):
    user, seq_request, libraries = _request_with_libraries(session, LB.ACCEPTED, LB.ACCEPTED)
    project = create_project(session, user)
    stored = create_sample(session, user, project)
    stored.status = SA.STORED
    no_status = create_sample(session, user, project)  # pooled submissions: status NULL
    session.save(stored, flush=True)
    actions.link_sample_library(session, stored.id, libraries[0].id)
    actions.link_sample_library(session, no_status.id, libraries[1].id)

    rule = ChildrenAll(R.REQUEST_SAMPLES, at_least(SA.STORED), nonempty=True)
    assert rule.evaluate(Snapshot(session), seq_request).holds


def test_children_none_and_any(session: SyncSession):
    _, seq_request, _ = _request_with_libraries(session, LB.POOLED, LB.ACCEPTED)
    snapshot = Snapshot(session)
    verdict = ChildrenNone(R.REQUEST_LIBRARIES, frozenset([LB.ACCEPTED, LB.STORED])).evaluate(snapshot, seq_request)
    assert not verdict.holds
    assert verdict.blockers[0].text == "1 ACCEPTED among the libraries of the request"
    assert ChildrenAny(R.REQUEST_LIBRARIES, frozenset([LB.POOLED])).evaluate(snapshot, seq_request).holds
    assert not ChildrenAny(R.REQUEST_LIBRARIES, frozenset([LB.SEQUENCED])).evaluate(snapshot, seq_request).holds


def test_blocker_sample_is_capped(session: SyncSession):
    statuses = [LB.ACCEPTED] * (BLOCKER_SAMPLE_SIZE + 3)
    _, seq_request, _ = _request_with_libraries(session, *statuses)
    blocker = ChildrenAll(R.REQUEST_LIBRARIES, at_least(LB.POOLED)).evaluate(Snapshot(session), seq_request).blockers[0]
    assert blocker.count == BLOCKER_SAMPLE_SIZE + 3
    assert len(blocker.sample_ids) == BLOCKER_SAMPLE_SIZE


def test_snapshot_queries_once_per_relation(session: SyncSession):
    _, seq_request, _ = _request_with_libraries(session, LB.POOLED, LB.SEQUENCED)
    snapshot = Snapshot(session)
    for rule in (
        ChildrenAll(R.REQUEST_LIBRARIES, at_least(LB.POOLED)),
        ChildrenAny(R.REQUEST_LIBRARIES, frozenset([LB.POOLED])),
        ChildrenNone(R.REQUEST_LIBRARIES, below(LB.POOLED)),
    ):
        assert rule.evaluate(snapshot, seq_request).holds
    assert snapshot.queries == 1


def test_combinators(session: SyncSession):
    _, seq_request, _ = _request_with_libraries(session, LB.ACCEPTED)
    snapshot = Snapshot(session)
    draft = StatusIn(frozenset([RQ.DRAFT]))
    accepted = StatusIn(frozenset([RQ.ACCEPTED]))
    pooled = ChildrenAll(R.REQUEST_LIBRARIES, at_least(LB.POOLED))

    both = All(accepted, pooled).evaluate(snapshot, seq_request)
    assert not both.holds and len(both.blockers) == 2
    assert AnyOf(accepted, draft).evaluate(snapshot, seq_request).holds
    assert not AnyOf(accepted, pooled).evaluate(snapshot, seq_request).holds
    assert Not(accepted).evaluate(snapshot, seq_request).holds
    assert (draft & ~accepted).evaluate(snapshot, seq_request).holds
    assert (accepted | draft).describe() == "status is ACCEPTED or status is DRAFT"
    assert Predicate("always", lambda s, o: True).evaluate(snapshot, seq_request).holds


def test_worker_guard_explains_why_not_prepared(session: SyncSession):
    _, seq_request, _ = _request_with_libraries(session, LB.POOLED, LB.ACCEPTED, LB.STORED)
    seq_request.status = RQ.SAMPLES_RECEIVED
    session.save(seq_request, flush=True)

    verdict = registry()["worker.request_prepared"].guard.evaluate(Snapshot(session), seq_request)
    assert not verdict.holds
    assert [b.text for b in verdict.blockers] == ["2 libraries of the request below POOLED (1 ACCEPTED, 1 STORED)"]


def test_worker_guard_holds_like_worker_query(session: SyncSession):
    _, seq_request, _ = _request_with_libraries(session, LB.POOLED, LB.SEQUENCED, LB.FAILED)
    seq_request.status = RQ.SAMPLES_RECEIVED
    session.save(seq_request, flush=True)
    assert registry()["worker.request_prepared"].guard.evaluate(Snapshot(session), seq_request).holds
