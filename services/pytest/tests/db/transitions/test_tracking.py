import pytest
import sqlalchemy as sa

from opengsync_db import SyncSession, models
from opengsync_db.categories import (
    LibraryStatus as LB, SeqRequestStatus as RQ, PoolStatus as PL, DeliveryStatus as DL, OperationKind, SubmissionType,
)
from opengsync_db.transitions import run_operation, UndeclaredTransition, request as request_ops, worker as worker_ops
from opengsync_db.transitions import tracking

from ..create_units import create_user, create_project, create_seq_request, create_library, create_sample, create_pool


def _runs(session: SyncSession, operation: str) -> list[models.OperationRun]:
    return list(session.execute(
        sa.select(models.OperationRun).where(models.OperationRun.operation == operation).order_by(models.OperationRun.id)
    ).scalars())


def _changes(session: SyncSession, entity_type: str, entity_id: int) -> list[models.StatusChange]:
    return list(session.execute(
        sa.select(models.StatusChange)
        .where(models.StatusChange.entity_type == entity_type, models.StatusChange.entity_id == entity_id)
        .order_by(models.StatusChange.id)
    ).scalars())


def _request(session: SyncSession, n_libraries: int = 2):
    user = create_user(session)
    seq_request = create_seq_request(session, user, submission_type=SubmissionType.RAW_SAMPLES)
    libraries = [create_library(session, user, seq_request) for _ in range(n_libraries)]
    session.commit()
    return user, seq_request, libraries


@pytest.fixture
def warnings(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    messages: list[str] = []
    monkeypatch.setattr(tracking, "_warned", set())
    monkeypatch.setattr(tracking.logger, "warning", lambda message, *a, **k: messages.append(message))
    return messages


def test_operation_records_one_run_with_all_changes(session: SyncSession):
    user, seq_request, libraries = _request(session)
    with run_operation(session, request_ops.SUBMIT, subject=seq_request, actor_id=user.id):
        seq_request.status = RQ.SUBMITTED
        for library in libraries:
            library.status = LB.SUBMITTED
    session.commit()

    [run] = _runs(session, "request.submit")
    assert run.kind == OperationKind.ACTION
    assert run.actor_id == user.id
    assert (run.subject_type, run.subject_id) == ("seq_request", seq_request.id)
    assert run.reason is None and run.comment is None
    assert {(c.entity_type, c.entity_id, c.from_status, c.to_status, c.declared) for c in run.changes} == {
        ("seq_request", seq_request.id, RQ.DRAFT.id, RQ.SUBMITTED.id, True),
        *(("library", lib.id, LB.DRAFT.id, LB.SUBMITTED.id, True) for lib in libraries),
    }


def test_operation_by_id_and_several_flushes(session: SyncSession):
    _, seq_request, libraries = _request(session)
    with run_operation(session, "request.submit"):
        seq_request.status = RQ.SUBMITTED
        session.flush()
        libraries[0].status = LB.SUBMITTED
        session.flush()
        libraries[1].status = LB.SUBMITTED
    session.commit()
    [run] = _runs(session, "request.submit")
    assert len(run.changes) == 3


def test_nested_operations(session: SyncSession):
    _, seq_request, libraries = _request(session, 1)
    with run_operation(session, request_ops.SUBMIT, subject=seq_request) as outer:
        with run_operation(session, request_ops.ACCEPT) as inner:
            seq_request.status = RQ.ACCEPTED
    session.commit()
    [parent] = _runs(session, "request.submit")
    [child] = _runs(session, "request.accept")
    assert parent.changes == []  # created as ancestor of the child run
    assert child.parent_run_id == parent.id
    assert outer.run_id == parent.id and inner.run_id == child.id


def test_rollback_discards_rows_and_run_is_recreated(session: SyncSession):
    _, seq_request, _ = _request(session, 0)
    with run_operation(session, request_ops.SUBMIT) as op:
        seq_request.status = RQ.SUBMITTED
        session.flush()
        first_run = op.run_id
        assert first_run is not None
        session.rollback()
        assert op.run_id is None
        seq_request.status = RQ.SUBMITTED
    session.commit()
    [run] = _runs(session, "request.submit")
    assert run.id != first_run
    assert [(c.from_status, c.to_status) for c in run.changes] == [(RQ.DRAFT.id, RQ.SUBMITTED.id)]


def test_insert_with_column_default_records_creation(session: SyncSession):
    user = create_user(session)
    with run_operation(session, "request.create"):
        seq_request = create_seq_request(session, user)  # status comes from the column default
    session.commit()
    [change] = _changes(session, "seq_request", seq_request.id)[-1:]
    assert (change.from_status, change.to_status, change.declared) == (None, RQ.DRAFT.id, True)
    assert change.run.operation == "request.create"


def test_insert_without_status_records_nothing(session: SyncSession):
    user = create_user(session)
    project = create_project(session, user)
    sample = create_sample(session, user, project)  # pooled-submission samples have no status
    session.commit()
    assert _changes(session, "sample", sample.id) == []


def test_expired_attribute_still_has_from_status(session: SyncSession):
    _, seq_request, [library] = _request(session, 1)
    library.status = LB.ACCEPTED
    session.commit()
    session.expire(library)
    with run_operation(session, "manual.edit_library"):
        library.status = LB.POOLED
    session.commit()
    assert [(c.from_status, c.to_status) for c in _changes(session, "library", library.id)[-1:]] == [(LB.ACCEPTED.id, LB.POOLED.id)]


def test_same_value_and_revert_write_nothing(session: SyncSession):
    _, _, [library] = _request(session, 1)
    before = len(_changes(session, "library", library.id))
    with run_operation(session, "manual.edit_library"):
        library.status = LB.DRAFT  # unchanged
        session.flush()
        library.status = LB.POOLED
        library.status = LB.DRAFT  # reverted before the flush
    session.commit()
    assert len(_changes(session, "library", library.id)) == before
    assert _runs(session, "manual.edit_library") == []


def test_deletes_are_not_recorded(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    session.commit()
    before = len(_changes(session, "pool", pool.id))
    session.delete(pool)
    session.commit()
    assert len(_changes(session, "pool", pool.id)) == before


def test_unattributed_change_is_recorded_with_location(session: SyncSession, warnings: list[str]):
    _, _, [library] = _request(session, 1)
    session.info["transitions.mode"] = "warn"
    library.status = LB.POOLED
    session.commit()
    change = _changes(session, "library", library.id)[-1]
    assert change.declared is False
    assert change.run.operation == "system.unattributed"
    assert change.run.kind == OperationKind.SYSTEM
    assert "test_tracking:test_unattributed_change_is_recorded_with_location" in change.run.reason
    assert len(warnings) == 1 and "outside an operation" in warnings[0]


def test_warnings_are_logged_once_per_location(session: SyncSession, warnings: list[str]):
    _, _, libraries = _request(session, 2)
    session.info["transitions.mode"] = "warn"
    for library in libraries:
        library.status = LB.POOLED
        session.flush()
    session.commit()
    assert len(warnings) == 1


def test_record_mode_is_silent(session: SyncSession, warnings: list[str]):
    _, _, [library] = _request(session, 1)
    library.status = LB.POOLED
    session.commit()
    assert warnings == []
    assert _changes(session, "library", library.id)[-1].run.operation == "system.unattributed"


def test_strict_mode_rejects_unattributed_change(session: SyncSession):
    _, _, [library] = _request(session, 1)
    session.info["transitions.mode"] = "strict"
    library.status = LB.POOLED
    with pytest.raises(UndeclaredTransition, match="outside an operation"):
        session.flush()
    session.rollback()


def test_strict_mode_rejects_undeclared_edge(session: SyncSession):
    _, seq_request, _ = _request(session, 0)
    session.info["transitions.mode"] = "strict"
    with pytest.raises(UndeclaredTransition, match="request.submit does not declare Request: DRAFT → FINISHED"):
        with run_operation(session, request_ops.SUBMIT):
            seq_request.status = RQ.FINISHED
    session.rollback()


def test_undeclared_edge_is_flagged(session: SyncSession):
    _, seq_request, _ = _request(session, 0)
    with run_operation(session, request_ops.SUBMIT):
        seq_request.status = RQ.FINISHED
    session.commit()
    assert _changes(session, "seq_request", seq_request.id)[-1].declared is False


def test_actor_comment_and_detail(session: SyncSession):
    user, _, [library] = _request(session, 1)
    other = create_user(session)
    tracking.set_actor(session, user.id)
    with run_operation(session, "manual.edit_library", comment="  QC failed, see BA report  ") as op:
        library.status = LB.FAILED
        op.detail(library, "lane 2")
    with run_operation(session, "manual.edit_library", actor_id=other.id):
        library.status = LB.ARCHIVED
    session.commit()
    first, second = _runs(session, "manual.edit_library")
    assert (first.actor_id, first.comment) == (user.id, "QC failed, see BA report")
    assert first.changes[0].detail == "lane 2"
    assert second.actor_id == other.id


def test_delivery_link_has_key(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    session.commit()
    with run_operation(session, "request.add_share_email"):
        seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(email="a@b.c"))
    session.commit()
    [change] = _changes(session, "seq_request_delivery_email_link", seq_request.id)
    assert (change.entity_key, change.from_status, change.to_status) == ("a@b.c", None, DL.PENDING.id)


def test_worker_operation_needs_reason():
    with pytest.raises(ValueError, match="worker.pool_sequenced: WORKER operations need a reason"):
        with run_operation(None, "worker.pool_sequenced", reason="   "):  # type: ignore[arg-type]
            pass
    with pytest.raises(ValueError, match="reason template .* needs 'folder'"):
        with run_operation(None, "worker.rf_folder_missing"):  # type: ignore[arg-type]
            pass


def test_reason_template_is_rendered(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    pool.status = PL.ACCEPTED
    session.commit()
    with run_operation(session, worker_ops.POOL_SEQUENCED):
        pool.status = PL.SEQUENCED
    with run_operation(session, "worker.rf_run_status", folder="/illumina/run_1", marker="RTAComplete.txt found"):
        pass  # no changes: no run row
    session.commit()
    [run] = _runs(session, "worker.pool_sequenced")
    assert run.kind == OperationKind.WORKER
    assert run.reason == "experiment of the pool is SEQUENCED, DEMULTIPLEXED or ARCHIVED"
    assert _runs(session, "worker.rf_run_status") == []


def test_history_rows_do_not_reach_the_unit_of_work(session: SyncSession):
    _, seq_request, _ = _request(session, 0)
    with run_operation(session, request_ops.SUBMIT):
        seq_request.status = RQ.SUBMITTED
        session.flush()
        assert not any(isinstance(o, (models.OperationRun, models.StatusChange)) for o in session.new)
    session.commit()
