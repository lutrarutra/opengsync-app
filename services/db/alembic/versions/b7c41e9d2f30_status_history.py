"""status history: operation_run, status_change, baseline, commit-time triggers

Revision ID: b7c41e9d2f30
Revises: a9d4e2b71c58
Create Date: 2026-10-14 18:00:00.000000

Every status change is recorded in status_change, grouped by operation_run (see
docs/state-transitions.md). Existing records get one baseline change (NULL -> current status):
history before this migration is unknown. Then every status column gets a deferred constraint
trigger: a commit that changes a status without a history row in the same transaction fails.

This migration keeps a frozen copy of opengsync_db.transitions.sql; tests compare the two.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b7c41e9d2f30"
down_revision: Union[str, Sequence[str], None] = "a9d4e2b71c58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, id column, key column) of every status-bearing table; all status columns are status_id
ENTITIES = [
    ("seq_request", "id", None),
    ("project", "id", None),
    ("sample", "id", None),
    ("library", "id", None),
    ("pool", "id", None),
    ("lab_prep", "id", None),
    ("experiment", "id", None),
    ("seq_run", "id", None),
    ("seq_request_delivery_email_link", "seq_request_id", "email"),
]

# operation_run.kind_id: 11 = MIGRATION; 10, 11, 12 (WORKER, MIGRATION, SYSTEM) must carry a reason
REASON_CHECK = "kind_id NOT IN (10, 11, 12) OR (reason IS NOT NULL AND length(btrim(reason)) > 0)"

TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION assert_status_history() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    new_row jsonb := to_jsonb(NEW);
    v_id bigint := (new_row ->> TG_ARGV[0])::bigint;
    v_key text := CASE WHEN TG_ARGV[1] = '' THEN NULL ELSE new_row ->> TG_ARGV[1] END;
    v_status smallint := (new_row ->> 'status_id')::smallint;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF (to_jsonb(OLD) ->> 'status_id') IS NOT DISTINCT FROM (new_row ->> 'status_id') THEN
            RETURN NULL;
        END IF;
    ELSIF v_status IS NULL THEN
        RETURN NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM status_change sc
        WHERE sc.entity_type = TG_TABLE_NAME
          AND sc.entity_id = v_id
          AND sc.entity_key IS NOT DISTINCT FROM v_key
          AND sc.to_status IS NOT DISTINCT FROM v_status
          AND sc.txid = txid_current()
    ) THEN
        RAISE EXCEPTION 'status change without history row: %.status_id of % % -> %', TG_TABLE_NAME, v_id, coalesce(v_key, ''), v_status
            USING ERRCODE = 'integrity_constraint_violation',
                  HINT = 'Change statuses through the ORM (opengsync_db.transitions) or with record_bulk_status_change().';
    END IF;
    RETURN NULL;
END
$$;
"""


def upgrade() -> None:
    op.create_table(
        "operation_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("kind_id", sa.SmallInteger(), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("lims_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("subject_type", sa.String(64), nullable=True),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("parent_run_id", sa.Integer(), sa.ForeignKey("operation_run.id", ondelete="SET NULL"), nullable=True),
        sa.Column("comment", sa.String(512), nullable=True),
        sa.Column("reason", sa.String(512), nullable=True),
        sa.Column("inferred", sa.Boolean(), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()")),
        sa.CheckConstraint(REASON_CHECK, name="ck_operation_run_reason"),
    )
    op.create_index("ix_operation_run_operation", "operation_run", ["operation"])
    op.create_index("ix_operation_run_actor_id", "operation_run", ["actor_id"])

    op.create_table(
        "status_change",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("operation_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("entity_key", sa.String(256), nullable=True),
        sa.Column("from_status", sa.SmallInteger(), nullable=True),
        sa.Column("to_status", sa.SmallInteger(), nullable=True),
        sa.Column("declared", sa.Boolean(), nullable=False),
        sa.Column("inferred", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.String(512), nullable=True),
        sa.Column("txid", sa.BigInteger(), nullable=False, server_default=sa.text("txid_current()")),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()")),
    )
    op.create_index("ix_status_change_run_id", "status_change", ["run_id"])
    op.create_index("ix_status_change_entity_timestamp", "status_change", ["entity_type", "entity_id", "timestamp_utc"])
    op.create_index("ix_status_change_entity_txid", "status_change", ["entity_type", "entity_id", "txid"])

    op.add_column("seq_request", sa.Column("route_override", sa.String(32), nullable=True))

    # Baseline: one change per existing record, NULL -> current status
    op.execute("""
        INSERT INTO operation_run (operation, kind_id, reason, inferred)
        VALUES ('migration.baseline', 11, 'status at the time status history was introduced', false)
    """)
    for table, id_col, key_col in ENTITIES:
        op.execute(f"""
            INSERT INTO status_change (run_id, entity_type, entity_id, entity_key, from_status, to_status, declared, inferred)
            SELECT (SELECT max(id) FROM operation_run WHERE operation = 'migration.baseline'),
                   '{table}', t.{id_col}, {f"t.{key_col}" if key_col else "NULL"}, NULL, t.status_id, true, false
            FROM {table} t
            WHERE t.status_id IS NOT NULL
        """)

    op.execute(TRIGGER_FUNCTION)
    for table, id_col, key_col in ENTITIES:
        op.execute(
            f"CREATE CONSTRAINT TRIGGER trg_{table}_status_history "
            f"AFTER INSERT OR UPDATE OF status_id ON {table} "
            f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            f"EXECUTE FUNCTION assert_status_history('{id_col}', '{key_col or ''}')"
        )


def downgrade() -> None:
    for table, _, _ in ENTITIES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_status_history ON {table}")
    op.execute("DROP FUNCTION IF EXISTS assert_status_history()")
    op.drop_column("seq_request", "route_override")
    op.drop_table("status_change")
    op.drop_table("operation_run")
