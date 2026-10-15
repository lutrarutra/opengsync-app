"""inferred status history from existing timestamp columns

Revision ID: c3e8f1a6b905
Revises: b7c41e9d2f30
Create Date: 2026-10-14 18:05:00.000000

Reconstructs what the timestamp columns tell about past status changes, marked inferred = true and
grouped under one 'migration.inferred' run without actor. The previous status is unknown (NULL).
Columns that are never written (seq_request.timestamp_finished_utc,
experiment.timestamp_finished_utc) are skipped. Separate from the baseline so it can be reverted
on its own. No status column changes, so the status triggers are not involved.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3e8f1a6b905"
down_revision: Union[str, Sequence[str], None] = "b7c41e9d2f30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RUN = "(SELECT max(id) FROM operation_run WHERE operation = 'migration.inferred')"
ISO = "'^[0-9]{4}-[0-9]{2}-[0-9]{2}'"

# (table, to_status id, timestamp expression, filter)
SOURCES = [
    # seq_request.status_id 1 = SUBMITTED
    ("seq_request", 1, "t.timestamp_submitted_utc", "t.timestamp_submitted_utc IS NOT NULL"),
    # sample.status_id 2 = STORED, library.status_id 4 = STORED, pool.status_id 3 = STORED
    ("sample", 2, "t.timestamp_stored_utc", "t.timestamp_stored_utc IS NOT NULL"),
    ("library", 4, "t.timestamp_stored_utc", "t.timestamp_stored_utc IS NOT NULL"),
    ("pool", 3, "t.timestamp_stored_utc", "t.timestamp_stored_utc IS NOT NULL"),
    # experiment / project status_id 0 = DRAFT
    ("experiment", 0, "t.timestamp_created_utc", "t.timestamp_created_utc IS NOT NULL"),
    ("project", 0, "t.timestamp_created_utc", "t.timestamp_created_utc IS NOT NULL"),
    # seq_run.status_id 1 = RUNNING, 2 = FINISHED; timestamps are ISO strings in a JSONB column
    ("seq_run", 1, "(t.timestamps ->> 'started')::timestamptz", f"(t.timestamps ->> 'started') ~ {ISO}"),
    ("seq_run", 2, "(t.timestamps ->> 'completed')::timestamptz", f"(t.timestamps ->> 'completed') ~ {ISO}"),
]


def upgrade() -> None:
    op.execute("""
        INSERT INTO operation_run (operation, kind_id, reason, inferred)
        VALUES ('migration.inferred', 11, 'inferred from existing timestamp columns', true)
    """)
    for table, to_status, timestamp, condition in SOURCES:
        op.execute(f"""
            INSERT INTO status_change (run_id, entity_type, entity_id, from_status, to_status, declared, inferred, timestamp_utc)
            SELECT {RUN}, '{table}', t.id, NULL, {to_status}, true, true, {timestamp}
            FROM {table} t
            WHERE {condition}
        """)


def downgrade() -> None:
    op.execute("DELETE FROM operation_run WHERE operation = 'migration.inferred'")
