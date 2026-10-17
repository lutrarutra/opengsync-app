"""Status history migrations (b7c41e9d2f30 baseline + triggers, c3e8f1a6b905 inferred history).

The database is cloned from the test template (current models), seeded, then rolled back to the
schema before status history (history tables, triggers and route_override dropped) and stamped
with the previous revision. That avoids replaying the whole migration chain from an empty database.
"""
import datetime as dt
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from opengsync_db import SyncDBHandler, models
from opengsync_db.categories import (
    LibraryStatus as LB, SampleStatus as SA, PoolStatus as PL, SeqRequestStatus as RQ, RunStatus as RN,
)
from opengsync_db.transitions.sql import drop_all_statements, FUNCTION_NAME

from ..conftest import _PG
from ..db.create_units import (
    create_user, create_project, create_seq_request, create_library, create_sample, create_pool, create_seq_run,
    create_experiment, create_lab_prep,
)
from opengsync_db.categories import ExperimentWorkFlow

BASELINE = "b7c41e9d2f30"
INFERRED = "c3e8f1a6b905"
RESTORE_PREPARING = "d5a7c3e9f142"
TABLES = [
    "seq_request", "project", "sample", "library", "pool", "lab_prep", "experiment", "seq_run", "seq_request_delivery_email_link",
]


def _alembic_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        for candidate in (parent / "alembic", parent / "services" / "db" / "alembic"):
            if (candidate / "env.py").exists():
                return candidate
    pytest.fail("alembic directory not found (is ./services/db/alembic mounted in compose.test.yaml?)")


def _config(connection: sa.Connection) -> Config:
    config = Config()
    config.set_main_option("script_location", str(_alembic_dir()))
    config.attributes["connection"] = connection
    return config


def _before_status_history() -> str:
    revision = ScriptDirectory.from_config(_config(None)).get_revision(BASELINE)  # type: ignore[arg-type]
    return revision.down_revision  # type: ignore[return-value]


def _seed(db_name: str) -> dict:
    db = SyncDBHandler(auto_commit=True, session_info={"transitions.mode": "record"})
    db.connect(**_PG, db=db_name)
    session = db.open_session()
    user = create_user(session)
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    seq_request.status = RQ.SUBMITTED
    seq_request.timestamp_submitted_utc = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)
    library = create_library(session, user, seq_request)
    library.status = LB.STORED
    library.timestamp_stored_utc = dt.datetime(2026, 2, 1, tzinfo=dt.timezone.utc)
    create_library(session, user, seq_request)
    stored_sample = create_sample(session, user, project)
    stored_sample.status = SA.STORED
    stored_sample.timestamp_stored_utc = dt.datetime(2026, 2, 2, tzinfo=dt.timezone.utc)
    create_sample(session, user, project)  # no status
    pool = create_pool(session, user, seq_request)
    pool.status = PL.STORED
    pool.timestamp_stored_utc = dt.datetime(2026, 2, 3, tzinfo=dt.timezone.utc)
    lab_prep = create_lab_prep(session, user)
    in_prep_accepted = create_library(session, user, seq_request)
    in_prep_accepted.status = LB.ACCEPTED
    in_prep_accepted.lab_prep_id = lab_prep.id
    in_prep_pooled = create_library(session, user, seq_request)
    in_prep_pooled.status = LB.POOLED
    in_prep_pooled.lab_prep_id = lab_prep.id
    outside_prep = create_library(session, user, seq_request)
    outside_prep.status = LB.ACCEPTED
    create_experiment(session, user, ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    run = create_seq_run(session)
    run.status = RN.FINISHED
    run.set_timestamp("started", dt.datetime(2026, 3, 1, 8, 0))
    run.set_timestamp("completed", dt.datetime(2026, 3, 2, 8, 0))
    seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(email="a@b.c"))
    session.commit()
    ids = {
        "seq_request": seq_request.id, "library": library.id, "sample": stored_sample.id, "pool": pool.id, "seq_run": run.id,
        "in_prep_accepted": in_prep_accepted.id, "in_prep_pooled": in_prep_pooled.id, "outside_prep": outside_prep.id,
    }
    db.close_session()
    db.close()
    return ids


def _drop_status_history(connection: sa.Connection) -> None:
    for statement in drop_all_statements():
        connection.execute(sa.text(statement))
    connection.execute(sa.text("DROP TABLE status_change"))
    connection.execute(sa.text("DROP TABLE operation_run"))
    connection.execute(sa.text("ALTER TABLE seq_request DROP COLUMN route_override"))


def _schema_objects(connection: sa.Connection) -> dict:
    return {
        "function": connection.execute(sa.text(f"SELECT pg_get_functiondef('{FUNCTION_NAME}'::regproc)")).scalar_one(),
        "triggers": set(connection.execute(sa.text(
            "SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE tgname LIKE 'trg_%_status_history'"
        )).scalars()),
        "check": connection.execute(sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_operation_run_reason'"
        )).scalar_one(),
    }


@pytest.fixture
def migrated_db(_admin_engine: sa.Engine, _template_db: str):
    db_name = f"mig{uuid.uuid4().hex}"
    with _admin_engine.connect() as conn:
        conn.execute(sa.text(f"CREATE DATABASE {db_name} TEMPLATE {_template_db}"))
    engine = sa.create_engine(SyncDBHandler.AdminURL(**_PG, db=db_name))
    try:
        with engine.connect() as conn:
            expected = _schema_objects(conn)
        ids = _seed(db_name)
        with engine.begin() as conn:
            _drop_status_history(conn)
        with engine.connect() as conn:
            command.stamp(_config(conn), _before_status_history())
            conn.commit()
            command.upgrade(_config(conn), INFERRED)
            conn.commit()
        yield engine, ids, expected
    finally:
        engine.dispose()
        with _admin_engine.connect() as conn:
            conn.execute(sa.text(f"DROP DATABASE {db_name} WITH (FORCE)"))


def test_baseline_has_one_change_per_record(migrated_db):
    engine, _, _ = migrated_db
    with engine.connect() as conn:
        runs = conn.execute(sa.text("SELECT id, kind_id, reason FROM operation_run WHERE operation = 'migration.baseline'")).all()
        assert len(runs) == 1 and runs[0].kind_id == 11 and runs[0].reason
        for table in TABLES:
            expected = conn.execute(sa.text(f"SELECT count(*) FROM {table} WHERE status_id IS NOT NULL")).scalar_one()
            actual = conn.execute(sa.text(
                "SELECT count(*) FROM status_change WHERE run_id = :run AND entity_type = :t AND NOT inferred"
            ), {"run": runs[0].id, "t": table}).scalar_one()
            assert actual == expected, table
            assert expected > 0, table
        mismatches = conn.execute(sa.text("""
            SELECT count(*) FROM status_change sc JOIN library l ON l.id = sc.entity_id
            WHERE sc.entity_type = 'library' AND sc.run_id = :run AND sc.to_status IS DISTINCT FROM l.status_id
        """), {"run": runs[0].id}).scalar_one()
        assert mismatches == 0
        key = conn.execute(sa.text(
            "SELECT entity_key FROM status_change WHERE entity_type = 'seq_request_delivery_email_link' AND run_id = :run"
        ), {"run": runs[0].id}).scalar_one()
        assert key == "a@b.c"
        assert conn.execute(sa.text("SELECT count(*) FROM status_change WHERE from_status IS NOT NULL AND run_id = :run"), {"run": runs[0].id}).scalar_one() == 0


def test_null_statuses_are_skipped(migrated_db):
    engine, _, _ = migrated_db
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM sample WHERE status_id IS NULL")).scalar_one() == 1
        assert conn.execute(sa.text("SELECT count(*) FROM status_change WHERE to_status IS NULL")).scalar_one() == 0


def test_inferred_history(migrated_db):
    engine, ids, _ = migrated_db
    with engine.connect() as conn:
        [run] = conn.execute(sa.text("SELECT id, inferred, actor_id FROM operation_run WHERE operation = 'migration.inferred'")).all()
        assert run.inferred and run.actor_id is None
        rows = {
            (r.entity_type, r.entity_id, r.to_status): r.timestamp_utc
            for r in conn.execute(sa.text("SELECT * FROM status_change WHERE run_id = :run"), {"run": run.id})
        }
        assert conn.execute(sa.text("SELECT bool_and(inferred) FROM status_change WHERE run_id = :run"), {"run": run.id}).scalar_one()
    assert rows[("seq_request", ids["seq_request"], RQ.SUBMITTED.id)] == dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)
    assert rows[("library", ids["library"], LB.STORED.id)] == dt.datetime(2026, 2, 1, tzinfo=dt.timezone.utc)
    assert rows[("sample", ids["sample"], SA.STORED.id)] == dt.datetime(2026, 2, 2, tzinfo=dt.timezone.utc)
    assert rows[("pool", ids["pool"], PL.STORED.id)] == dt.datetime(2026, 2, 3, tzinfo=dt.timezone.utc)
    assert ("seq_run", ids["seq_run"], RN.RUNNING.id) in rows
    assert ("seq_run", ids["seq_run"], RN.FINISHED.id) in rows
    assert not any(t == "seq_request" and s == RQ.FINISHED.id for t, _, s in rows)


def test_migration_installs_the_same_triggers_as_create_all(migrated_db):
    engine, _, expected = migrated_db
    with engine.connect() as conn:
        assert _schema_objects(conn) == expected


def test_raw_status_update_fails_after_migration(migrated_db):
    engine, ids, _ = migrated_db
    with pytest.raises(sa.exc.IntegrityError, match="status change without history row"):
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE library SET status_id = 5 WHERE id = :id"), {"id": ids["library"]})


def test_downgrade_and_upgrade_again(migrated_db):
    engine, _, expected = migrated_db
    with engine.connect() as conn:
        command.downgrade(_config(conn), BASELINE)
        conn.commit()
        assert conn.execute(sa.text("SELECT count(*) FROM operation_run WHERE operation = 'migration.inferred'")).scalar_one() == 0
        command.downgrade(_config(conn), _before_status_history())
        conn.commit()
        assert not sa.inspect(conn).has_table("status_change")
        assert not sa.inspect(conn).has_table("operation_run")
        assert "route_override" not in {c["name"] for c in sa.inspect(conn).get_columns("seq_request")}
        assert conn.execute(sa.text("SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'trg_%_status_history'")).scalar_one() == 0
        # Not "head": the database comes from create_all, so later migrations' tables already exist
        command.upgrade(_config(conn), RESTORE_PREPARING)
        conn.commit()
        assert _schema_objects(conn) == expected


def test_restore_preparing(migrated_db):
    engine, ids, _ = migrated_db
    with engine.connect() as conn:
        command.upgrade(_config(conn), RESTORE_PREPARING)
        conn.commit()
        status = dict(conn.execute(sa.text("SELECT id, status_id FROM library")).all())
        assert status[ids["in_prep_accepted"]] == LB.PREPARING.id
        assert status[ids["in_prep_pooled"]] == LB.POOLED.id
        assert status[ids["outside_prep"]] == LB.ACCEPTED.id
        [run] = conn.execute(sa.text("SELECT id, kind_id, reason FROM operation_run WHERE operation = 'migration.restore_preparing'")).all()
        assert run.kind_id == 11 and "d9685235" in run.reason
        changes = conn.execute(sa.text("SELECT entity_id, from_status, to_status FROM status_change WHERE run_id = :run"), {"run": run.id}).all()
        assert [tuple(c) for c in changes] == [(ids["in_prep_accepted"], LB.ACCEPTED.id, LB.PREPARING.id)]
