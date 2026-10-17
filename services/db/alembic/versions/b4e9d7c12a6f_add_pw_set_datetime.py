"""add password set datetime to users

Revision ID: b4e9d7c12a6f
Revises: 8f2c1d4a7b90
Create Date: 2026-09-09 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4e9d7c12a6f"
down_revision: Union[str, Sequence[str], None] = "8f2c1d4a7b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lims_user",
        sa.Column("pw_set_datetime", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lims_user", "pw_set_datetime")
