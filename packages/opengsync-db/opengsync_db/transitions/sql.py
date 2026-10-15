"""Database side of status history: the commit-time trigger and a helper for data migrations.

Every status column has a deferred constraint trigger: when a transaction commits, each status
change it made must have a matching `status_change` row written in the same transaction (same
`txid`). The ORM hook in `tracking.py` writes those rows; raw SQL must use
`record_bulk_status_change()`. Deletes are not checked.

Alembic migrations keep a frozen copy of this SQL; a test compares the installed triggers.
"""
from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from .entities import ENTITIES, Entity

STATUS_COLUMN = "status_id"
FUNCTION_NAME = "assert_status_history"

IMPLICIT_KIND_IDS = (10, 11, 12)
"""OperationKind ids of WORKER, MIGRATION and SYSTEM: these runs must carry a reason."""

REASON_CHECK = f"kind_id NOT IN ({', '.join(map(str, IMPLICIT_KIND_IDS))}) OR (reason IS NOT NULL AND length(btrim(reason)) > 0)"

TRIGGER_FUNCTION = f"""
CREATE OR REPLACE FUNCTION {FUNCTION_NAME}() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    new_row jsonb := to_jsonb(NEW);
    v_id bigint := (new_row ->> TG_ARGV[0])::bigint;
    v_key text := CASE WHEN TG_ARGV[1] = '' THEN NULL ELSE new_row ->> TG_ARGV[1] END;
    v_status smallint := (new_row ->> '{STATUS_COLUMN}')::smallint;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF (to_jsonb(OLD) ->> '{STATUS_COLUMN}') IS NOT DISTINCT FROM (new_row ->> '{STATUS_COLUMN}') THEN
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
        RAISE EXCEPTION 'status change without history row: %.{STATUS_COLUMN} of % % -> %', TG_TABLE_NAME, v_id, coalesce(v_key, ''), v_status
            USING ERRCODE = 'integrity_constraint_violation',
                  HINT = 'Change statuses through the ORM (opengsync_db.transitions) or with record_bulk_status_change().';
    END IF;
    RETURN NULL;
END
$$;
""".strip()


def trigger_name(entity: Entity) -> str:
    return f"trg_{entity.name}_status_history"


def create_trigger(entity: Entity) -> str:
    return (
        f"CREATE CONSTRAINT TRIGGER {trigger_name(entity)} "
        f"AFTER INSERT OR UPDATE OF {STATUS_COLUMN} ON {entity.name} "
        f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        f"EXECUTE FUNCTION {FUNCTION_NAME}('{entity.id_attr}', '{entity.key_attr or ''}')"
    )


def drop_trigger(entity: Entity) -> str:
    return f"DROP TRIGGER IF EXISTS {trigger_name(entity)} ON {entity.name}"


def create_all_statements() -> list[str]:
    return [TRIGGER_FUNCTION] + [create_trigger(e) for e in ENTITIES]


def drop_all_statements() -> list[str]:
    return [drop_trigger(e) for e in ENTITIES] + [f"DROP FUNCTION IF EXISTS {FUNCTION_NAME}()"]


def record_bulk_status_change(
    connection: sa.Connection,
    entity: Entity,
    where_sql: str,
    to_status: Any,
    operation: str,
    reason: str,
    kind_id: int = 11,
    params: dict[str, Any] | None = None,
) -> int:
    """Sets the status of all `entity` rows matching `where_sql` and records the history, in one statement.

    For data migrations and maintenance scripts; normal code goes through the ORM. Rows already at
    `to_status` are skipped. Returns the number of changed rows. `where_sql` is trusted SQL against
    the entity table (aliased `t`); pass values through `params`.

        record_bulk_status_change(
            op.get_bind(), entities.LIBRARY, "t.lab_prep_id IS NOT NULL AND t.status_id < 3", 3,
            "migration.restore_preparing", "library is in a lab prep",
        )
    """
    to_id = getattr(to_status, "id", to_status)
    key_col = f"t.{entity.key_attr}" if entity.key_attr else "NULL"
    stmt = sa.text(f"""
        WITH run AS (
            INSERT INTO operation_run (operation, kind_id, reason, inferred, timestamp_utc)
            VALUES (:operation, :kind_id, :reason, false, clock_timestamp())
            RETURNING id
        ),
        old AS (
            SELECT t.{entity.id_attr} AS entity_id, {key_col} AS entity_key, t.{STATUS_COLUMN} AS from_status
            FROM {entity.name} t
            WHERE ({where_sql}) AND t.{STATUS_COLUMN} IS DISTINCT FROM :to_status
            FOR UPDATE
        ),
        changed AS (
            UPDATE {entity.name} t SET {STATUS_COLUMN} = :to_status
            FROM old
            WHERE t.{entity.id_attr} = old.entity_id
              {f"AND t.{entity.key_attr} = old.entity_key" if entity.key_attr else ""}
            RETURNING old.entity_id, old.entity_key, old.from_status
        )
        INSERT INTO status_change (run_id, entity_type, entity_id, entity_key, from_status, to_status, declared, inferred, timestamp_utc)
        SELECT run.id, :entity_type, changed.entity_id, changed.entity_key, changed.from_status, :to_status, true, false, clock_timestamp()
        FROM changed, run
        RETURNING id
    """)
    result = connection.execute(stmt, {
        **(params or {}), "operation": operation, "kind_id": kind_id, "reason": reason,
        "to_status": to_id, "entity_type": entity.name,
    })
    return len(result.fetchall())
