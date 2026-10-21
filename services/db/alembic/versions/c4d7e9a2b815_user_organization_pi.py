"""user organization (institute, department) and PI

Revision ID: c4d7e9a2b815
Revises: b8e2d4f1c937
Create Date: 2026-10-21 12:00:00.000000

Free-text columns; the forms normalize new values to existing spellings, so no lookup tables.
Existing users keep them empty until they edit their profile or are reactivated.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c4d7e9a2b815"
down_revision: Union[str, Sequence[str], None] = "b8e2d4f1c937"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lims_user", sa.Column("institute", sa.String(256), nullable=True))
    op.add_column("lims_user", sa.Column("department", sa.String(256), nullable=True))
    op.add_column("lims_user", sa.Column("pi_name", sa.String(128), nullable=True))
    op.add_column("lims_user", sa.Column("pi_email", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("lims_user", "pi_email")
    op.drop_column("lims_user", "pi_name")
    op.drop_column("lims_user", "department")
    op.drop_column("lims_user", "institute")
