import pytest
import sqlalchemy as sa

from opengsync_db import SyncSession
from opengsync_db.categories import (
    LibraryStatus as LB, SeqRequestStatus as RQ, PoolStatus as PL, PrepStatus as PR, SubmissionType, ExperimentWorkFlow,
)
from opengsync_db.transitions import run_operation, status

from ..create_units import create_user, create_seq_request, create_library, create_pool, create_lab_prep, create_experiment


def _request(session: SyncSession, submission_type=SubmissionType.RAW_SAMPLES, request_status=RQ.DRAFT, *library_statuses: LB):
    user = create_user(session)
    seq_request = create_seq_request(session, user, submission_type=submission_type)
    seq_request.status = request_status
    libraries = []
    for library_status in library_statuses:
        library = create_library(session, user, seq_request)
        library.status = library_status
        libraries.append(library)
    session.commit()
    return user, seq_request, libraries


def _way(ways, op_id: str) -> status.WayReport:
    return next(w for w in ways if w.operation.id == op_id)


def test_draft_request_next_step_is_submit(session: SyncSession):
    _, seq_request, _ = _request(session, SubmissionType.RAW_SAMPLES, RQ.DRAFT, LB.DRAFT)
    report = status.build(session, seq_request)

    assert report.route.id == "raw_samples" and report.route_inferred
    assert [s.state for s in report.steps][:2] == ["current", "upcoming"]
    assert report.next_title == "Submit"
    submit = _way(report.next_ways, "request.submit")
    assert submit.started_here and not submit.available  # no auth form uploaded yet
    assert [b.text for b in report.next_blockers] == ["not: request is submittable (auth form uploaded, libraries annotated)"]
    # 'status is DRAFT, needs ...' is not shown: unarchive does not apply to a draft
    assert all(w.operation.id != "request.unarchive" for w in report.other_ways)


def test_samples_received_request_explains_what_is_next(session: SyncSession):
    _, seq_request, _ = _request(session, SubmissionType.RAW_SAMPLES, RQ.SAMPLES_RECEIVED, LB.POOLED, LB.ACCEPTED, LB.STORED)
    report = status.build(session, seq_request)

    states = {s.step.id: s.state for s in report.steps}
    assert states["submit"] == states["review"] == states["receive"] == "done"
    assert states["prep"] == "current"
    assert report.next_title == "Library prep"
    assert [b.text for b in report.next_blockers] == ["1 ACCEPTED among the libraries of the request"]
    add = _way(report.next_ways, "prep.add_libraries")
    assert not add.started_here  # done from the lab prep page

    worker = _way(report.other_ways, "worker.request_prepared")
    assert worker.automatic and worker.started_here and not worker.available
    assert [b.text for b in worker.relevant_blockers] == ["2 libraries of the request below POOLED (1 ACCEPTED, 1 STORED)"]
    assert not _way(report.other_ways, "prep.complete").started_here
    assert all(w.operation.id != "request.unarchive" for w in report.other_ways)


def test_optional_step_is_skipped_once_passed(session: SyncSession):
    _, seq_request, _ = _request(session, SubmissionType.RAW_SAMPLES, RQ.DATA_PROCESSING, LB.SEQUENCED)
    states = {s.step.id: s.state for s in status.build(session, seq_request).steps}
    assert states["mux"] == "done"  # done_when: request ≥ PREPARED
    assert states["sequence"] == "done" and states["release"] == "current"


def test_qc_only_route(session: SyncSession):
    _, seq_request, _ = _request(session, SubmissionType.QC_ONLY, RQ.SAMPLES_RECEIVED, LB.QC_PENDING)
    report = status.build(session, seq_request)
    assert report.route.id == "qc_only"
    assert {s.step.id: s.state for s in report.steps}["qc"] == "current"


def test_pinned_route(session: SyncSession):
    _, seq_request, _ = _request(session, SubmissionType.RAW_SAMPLES)
    seq_request.route_override = "pooled_libraries"
    session.commit()
    report = status.build(session, seq_request)
    assert report.route.id == "pooled_libraries" and not report.route_inferred


def test_report_query_count_is_bounded(session: SyncSession):
    _, seq_request, _ = _request(session, SubmissionType.RAW_SAMPLES, RQ.SAMPLES_RECEIVED, *([LB.ACCEPTED] * 30))
    statements: list[str] = []

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    engine = session.get_bind()
    sa.event.listen(engine, "before_cursor_execute", count)
    try:
        status.build(session, seq_request)
    finally:
        sa.event.remove(engine, "before_cursor_execute", count)
    # one GROUP BY per child relation plus capped blocker samples, independent of the number of libraries
    assert len(statements) < 40


@pytest.mark.parametrize("factory", ["lab_prep", "experiment"])
def test_other_pages(session: SyncSession, factory: str):
    user = create_user(session)
    obj = create_lab_prep(session, user) if factory == "lab_prep" else create_experiment(session, user, ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    session.commit()
    report = status.build(session, obj)
    assert report.route is None
    if factory == "lab_prep":
        assert report.next_title == PR.COMPLETED.display_name
        complete = _way(report.next_ways, "prep.complete")
        assert complete.started_here and complete.available


def test_history(session: SyncSession):
    user, seq_request, [library] = _request(session, SubmissionType.RAW_SAMPLES, RQ.DRAFT, LB.DRAFT)
    with run_operation(session, "request.submit", subject=seq_request, actor_id=user.id):
        seq_request.status = RQ.SUBMITTED
        library.status = LB.SUBMITTED
    with run_operation(session, "manual.edit_library", comment="typo"):
        library.status = LB.FAILED
    session.commit()

    entries = status.history(session, seq_request)
    submit = next(e for e in entries if e.operation == "request.submit")
    assert submit.own_change == (RQ.DRAFT.id, RQ.SUBMITTED.id)
    assert submit.actor_id == user.id
    assert submit.related_changes == {("library", LB.DRAFT.id, LB.SUBMITTED.id): 1}
    assert all(e.operation != "manual.edit_library" for e in entries)  # did not touch the request

    library_entries = status.history(session, library)
    assert [e.operation for e in library_entries][:2] == ["manual.edit_library", "request.submit"]
    assert library_entries[0].comment == "typo"


def test_history_counts_only_related_changes(session: SyncSession):
    user, seq_request, [library] = _request(session, SubmissionType.RAW_SAMPLES, RQ.DRAFT, LB.DRAFT)
    _, other_request, [other_library] = _request(session, SubmissionType.RAW_SAMPLES, RQ.DRAFT, LB.DRAFT)
    with run_operation(session, "request.submit", subject=seq_request):
        seq_request.status = RQ.SUBMITTED
        library.status = LB.SUBMITTED
        other_library.status = LB.SUBMITTED  # not related to seq_request
    session.commit()

    [entry] = [e for e in status.history(session, seq_request) if e.operation == "request.submit"]
    assert entry.related_changes == {("library", LB.DRAFT.id, LB.SUBMITTED.id): 1}


def test_history_hides_other_changes_of_migrations(session: SyncSession):
    from opengsync_db.transitions.sql import record_bulk_status_change
    from opengsync_db.transitions import entities

    _, seq_request, [library] = _request(session, SubmissionType.RAW_SAMPLES, RQ.ACCEPTED, LB.ACCEPTED)
    record_bulk_status_change(
        session.connection(), entities.SEQ_REQUEST, "t.id = :id", RQ.SAMPLES_RECEIVED, "migration.test", "test", params={"id": seq_request.id},
    )
    record_bulk_status_change(
        session.connection(), entities.LIBRARY, "t.id = :id", LB.PREPARING, "migration.test", "test", params={"id": library.id},
    )
    session.commit()
    entries = [e for e in status.history(session, seq_request) if e.operation == "migration.test"]
    assert len(entries) == 1 and entries[0].related_changes == {}
    assert entries[0].own_change == (RQ.ACCEPTED.id, RQ.SAMPLES_RECEIVED.id)
