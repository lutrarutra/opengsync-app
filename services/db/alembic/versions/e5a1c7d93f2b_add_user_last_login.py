"""add last login datetime to users

Revision ID: e5a1c7d93f2b
Revises: 2c2e2dbfff47
Create Date: 2026-10-12 16:00:00.000000

Existing users are backfilled with the migration time so the inactivity job gives them a full
grace period instead of deactivating everyone on its first run.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5a1c7d93f2b"
down_revision: Union[str, Sequence[str], None] = "2c2e2dbfff47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lims_user",
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE lims_user SET last_login = now()")


def downgrade() -> None:
    op.drop_column("lims_user", "last_login")
