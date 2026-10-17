"""restore PREPARING for libraries in a lab prep

Revision ID: d5a7c3e9f142
Revises: c3e8f1a6b905
Create Date: 2026-10-14 20:00:00.000000

Adding libraries to a lab prep used to set them to PREPARING (LabPrepBP.add_library). Commit
d9685235 (2026-06-10) replaced that with a plain append, so libraries added since then stayed
below PREPARING. Adding sets PREPARING again; this migration fixes the libraries already in a prep.
The change is recorded in the status history (run 'migration.restore_preparing'), in the same
statement, so the status history trigger is satisfied.

Self-contained (no opengsync_db imports): alembic loads every revision file, also with an older
package installed. Same SQL as opengsync_db.transitions.sql.record_bulk_status_change.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d5a7c3e9f142"
down_revision: Union[str, Sequence[str], None] = "c3e8f1a6b905"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# library.status_id: 0 = DRAFT, 1 = SUBMITTED, 2 = ACCEPTED, 3 = PREPARING; operation_run.kind_id 11 = MIGRATION
PREPARING = 3
REASON = "restore PREPARING lost in d9685235 (2026-06-10): library is in a lab prep"


def upgrade() -> None:
    op.execute(f"""
        WITH run AS (
            INSERT INTO operation_run (operation, kind_id, reason, inferred, timestamp_utc)
            VALUES ('migration.restore_preparing', 11, '{REASON}', false, clock_timestamp())
            RETURNING id
        ),
        old AS (
            SELECT t.id AS entity_id, t.status_id AS from_status
            FROM library t
            WHERE t.lab_prep_id IS NOT NULL AND t.status_id < {PREPARING}
            FOR UPDATE
        ),
        changed AS (
            UPDATE library t SET status_id = {PREPARING}
            FROM old
            WHERE t.id = old.entity_id
            RETURNING old.entity_id, old.from_status
        )
        INSERT INTO status_change (run_id, entity_type, entity_id, entity_key, from_status, to_status, declared, inferred, timestamp_utc)
        SELECT run.id, 'library', changed.entity_id, NULL, changed.from_status, {PREPARING}, true, false, clock_timestamp()
        FROM changed, run
    """)


def downgrade() -> None:
    # The restored libraries can't be told apart from other PREPARING libraries
    pass
