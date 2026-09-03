"""add principal investigator contact to sequencing requests

Revision ID: 8f2c1d4a7b90
Revises: c3e8a91f4b20
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f2c1d4a7b90"
down_revision: Union[str, Sequence[str], None] = "c3e8a91f4b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "seq_request",
        sa.Column("pi_contact_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "seq_request_pi_contact_id_fkey",
        "seq_request",
        "contact",
        ["pi_contact_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "seq_request_pi_contact_id_fkey",
        "seq_request",
        type_="foreignkey",
    )
    op.drop_column("seq_request", "pi_contact_id")
