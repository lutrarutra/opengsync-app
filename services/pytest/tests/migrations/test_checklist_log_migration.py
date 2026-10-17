"""Checklist log migrations (a3f9c2e7b614 checklist_log, b8e2d4f1c937 experiment checklist).

Like test_status_history_migration: the database is cloned from the test template (current models),
the objects of these migrations are dropped, the previous revision is stamped and the migrations
must recreate exactly what the models define.
"""
import uuid

import pytest
import sqlalchemy as sa
from alembic import command

from opengsync_db import SyncDBHandler

from ..conftest import _PG
from .test_status_history_migration import _config, RESTORE_PREPARING


def _schema(connection: sa.Connection) -> dict:
    inspector = sa.inspect(connection)
    return {
        "columns": {(c["name"], str(c["type"]), c["nullable"]) for c in inspector.get_columns("checklist_log")},
        "foreign_keys": {
            (tuple(fk["constrained_columns"]), fk["referred_table"], fk["options"].get("ondelete"))
            for fk in inspector.get_foreign_keys("checklist_log")
        },
        "indexes": {(ix["name"], tuple(ix["column_names"])) for ix in inspector.get_indexes("checklist_log")},
        "experiment_manual_checklist": next(str(c["type"]) for c in inspector.get_columns("experiment") if c["name"] == "manual_checklist"),
    }


@pytest.fixture
def engine(_admin_engine: sa.Engine, _template_db: str):
    db_name = f"mig{uuid.uuid4().hex}"
    with _admin_engine.connect() as conn:
        conn.execute(sa.text(f"CREATE DATABASE {db_name} TEMPLATE {_template_db}"))
    engine = sa.create_engine(SyncDBHandler.AdminURL(**_PG, db=db_name))
    try:
        yield engine
    finally:
        engine.dispose()
        with _admin_engine.connect() as conn:
            conn.execute(sa.text(f"DROP DATABASE {db_name} WITH (FORCE)"))


def test_migrations_match_models(engine: sa.Engine):
    with engine.connect() as conn:
        expected = _schema(conn)
        conn.execute(sa.text("DROP TABLE checklist_log"))
        conn.execute(sa.text("ALTER TABLE experiment DROP COLUMN manual_checklist"))
        conn.commit()
        command.stamp(_config(conn), RESTORE_PREPARING)
        conn.commit()

        command.upgrade(_config(conn), "b8e2d4f1c937")
        conn.commit()
        assert _schema(conn) == expected

        command.downgrade(_config(conn), RESTORE_PREPARING)
        conn.commit()
        assert not sa.inspect(conn).has_table("checklist_log")
        assert "manual_checklist" not in {c["name"] for c in sa.inspect(conn).get_columns("experiment")}
