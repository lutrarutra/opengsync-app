import pytest
import sqlalchemy as sa
from sqlalchemy import exc

from opengsync_db import SyncSession, models
from opengsync_db.categories import LibraryStatus as LB, SampleStatus as SA
from opengsync_db.transitions import entities as E, run_operation
from opengsync_db.transitions.sql import record_bulk_status_change, trigger_name

from ..create_units import create_user, create_project, create_seq_request, create_library, create_sample


def _library(session: SyncSession) -> models.Library:
    user = create_user(session)
    library = create_library(session, user, create_seq_request(session, user))
    session.commit()
    return library


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_implicit_run_needs_reason(session: SyncSession, reason: str | None):
    with pytest.raises(exc.IntegrityError, match="ck_operation_run_reason"):
        session.execute(sa.text(
            "INSERT INTO operation_run (operation, kind_id, reason, inferred) VALUES ('worker.x', 10, :reason, false)"
        ), {"reason": reason})
    session.rollback()


def test_action_run_needs_no_reason(session: SyncSession):
    session.execute(sa.text("INSERT INTO operation_run (operation, kind_id, inferred) VALUES ('request.submit', 0, false)"))
    session.commit()


def test_raw_status_update_fails_at_commit(session: SyncSession):
    library = _library(session)
    session.execute(sa.text("UPDATE library SET status_id = :s WHERE id = :id"), {"s": LB.POOLED.id, "id": library.id})
    with pytest.raises(exc.IntegrityError, match="status change without history row: library.status_id"):
        session.commit()
    session.rollback()


def test_raw_update_to_same_status_passes(session: SyncSession):
    library = _library(session)
    session.execute(sa.text("UPDATE library SET status_id = status_id WHERE id = :id"), {"id": library.id})
    session.commit()


def test_orm_change_passes(session: SyncSession):
    library = _library(session)
    with run_operation(session, "manual.edit_library"):
        library.status = LB.POOLED
    session.commit()


def test_null_sample_insert_passes(session: SyncSession):
    user = create_user(session)
    create_sample(session, user, create_project(session, user))
    session.commit()


def test_sample_set_to_null_is_recorded(session: SyncSession):
    user = create_user(session)
    sample = create_sample(session, user, create_project(session, user))
    sample.status = SA.STORED
    session.commit()
    with run_operation(session, "manual.edit_sample"):
        sample.status = None
    session.commit()


def test_bulk_helper_records_history(session: SyncSession):
    library = _library(session)
    other = _library(session)
    changed = record_bulk_status_change(
        session.connection(), E.LIBRARY, "t.id = :id", LB.PREPARING, "migration.test", "test reason", params={"id": library.id},
    )
    session.commit()
    assert changed == 1
    change = session.execute(
        sa.select(models.StatusChange).where(models.StatusChange.entity_type == "library", models.StatusChange.entity_id == library.id)
        .order_by(models.StatusChange.id.desc()).limit(1)
    ).scalar_one()
    assert (change.from_status, change.to_status) == (LB.DRAFT.id, LB.PREPARING.id)
    assert change.run.operation == "migration.test" and change.run.reason == "test reason"
    session.refresh(other)
    assert other.status == LB.DRAFT

    # already at the target status: nothing changes
    assert record_bulk_status_change(
        session.connection(), E.LIBRARY, "t.id = :id", LB.PREPARING, "migration.test", "again", params={"id": library.id},
    ) == 0
    session.commit()


def test_delivery_link_raw_update_fails(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(email="a@b.c"))
    session.commit()
    session.execute(sa.text("UPDATE seq_request_delivery_email_link SET status_id = 1 WHERE seq_request_id = :id"), {"id": seq_request.id})
    with pytest.raises(exc.IntegrityError, match="seq_request_delivery_email_link.status_id"):
        session.commit()
    session.rollback()


def test_every_entity_has_a_trigger(session: SyncSession):
    names = set(session.execute(sa.text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")).scalars())
    assert {trigger_name(e) for e in E.ENTITIES} <= names
