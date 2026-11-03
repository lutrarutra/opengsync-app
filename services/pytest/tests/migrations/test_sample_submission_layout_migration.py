"""Sample submission layout migration (e2b6f8a1c437).

Like test_checklist_log_migration: the database is cloned from the test template (current models),
the objects of the migration are dropped, the previous revision is stamped and the migration
must recreate exactly what the models define.
"""
import pytest
import sqlalchemy as sa
from alembic import command

from .test_checklist_log_migration import engine  # noqa: F401 (fixture)
from .test_status_history_migration import _config

REVISION = "e2b6f8a1c437"
PREVIOUS = "c4d7e9a2b815"
TABLE = "sample_submission_layout"


def _schema(connection: sa.Connection) -> dict:
    inspector = sa.inspect(connection)
    return {
        "columns": {(c["name"], str(c["type"]), c["nullable"]) for c in inspector.get_columns(TABLE)},
        "foreign_keys": {
            (tuple(fk["constrained_columns"]), fk["referred_table"], fk["options"].get("ondelete"))
            for fk in inspector.get_foreign_keys(TABLE)
        },
        "indexes": {(ix["name"], tuple(ix["column_names"])) for ix in inspector.get_indexes(TABLE)},
        "unique": {(uc["name"], tuple(uc["column_names"])) for uc in inspector.get_unique_constraints(TABLE)},
        "checks": {ck["name"] for ck in inspector.get_check_constraints(TABLE)},
        "seq_request_column": next(
            (str(c["type"]), c["nullable"]) for c in inspector.get_columns("seq_request") if c["name"] == "submission_layout_type_id"
        ),
    }


def test_migration_matches_models(engine: sa.Engine):  # noqa: F811
    with engine.connect() as conn:
        expected = _schema(conn)
        conn.execute(sa.text(f"DROP TABLE {TABLE}"))
        conn.execute(sa.text("ALTER TABLE seq_request DROP COLUMN submission_layout_type_id"))
        conn.commit()
        command.stamp(_config(conn), PREVIOUS)
        conn.commit()

        command.upgrade(_config(conn), REVISION)
        conn.commit()
        assert _schema(conn) == expected

        command.downgrade(_config(conn), PREVIOUS)
        conn.commit()
        assert not sa.inspect(conn).has_table(TABLE)
        assert "submission_layout_type_id" not in {c["name"] for c in sa.inspect(conn).get_columns("seq_request")}


def test_one_item_per_row_enforced(engine: sa.Engine):  # noqa: F811
    with engine.connect() as conn:
        with pytest.raises(sa.exc.IntegrityError, match="ck_sample_submission_layout_one_item"):
            conn.execute(sa.text(f"INSERT INTO {TABLE} (seq_request_id, position) VALUES (1, 'A1')"))
