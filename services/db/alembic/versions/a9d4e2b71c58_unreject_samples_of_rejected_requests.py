"""reset samples rejected through seq request rejection to draft

Revision ID: a9d4e2b71c58
Revises: e5a1c7d93f2b
Create Date: 2026-10-14 12:00:00.000000

Rejecting a sequencing request used to set its draft samples to REJECTED. REJECTED now means the
sample failed during library preparation and blocks re-using the sample name, so samples of rejected
requests are reset to DRAFT. Samples rejected otherwise (e.g. manually) keep their status.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a9d4e2b71c58"
down_revision: Union[str, Sequence[str], None] = "e5a1c7d93f2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sample.status_id: 0 = DRAFT, 11 = REJECTED; seq_request.status_id: 11 = REJECTED
    op.execute("""
        UPDATE sample SET status_id = 0
        WHERE status_id = 11
          AND id IN (
            SELECT sll.sample_id
            FROM sample_library_link sll
            JOIN library l ON l.id = sll.library_id
            JOIN seq_request sr ON sr.id = l.seq_request_id
            WHERE sr.status_id = 11
          )
    """)


def downgrade() -> None:
    # Reset samples can't be told apart from other draft samples
    pass
