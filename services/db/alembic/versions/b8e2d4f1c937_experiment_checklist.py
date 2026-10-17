"""experiment checklist: manually checked steps and their log

Revision ID: b8e2d4f1c937
Revises: a3f9c2e7b614
Create Date: 2026-10-17 15:00:00.000000

"Check Barcode Clashes" of the experiment checklist is checked by hand: the state is stored in
experiment.manual_checklist, every check and uncheck in checklist_log.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "b8e2d4f1c937"
down_revision: Union[str, Sequence[str], None] = "a3f9c2e7b614"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("experiment", sa.Column("manual_checklist", postgresql.JSONB(), nullable=True))
    op.add_column(
        "checklist_log",
        sa.Column("experiment_id", sa.Integer(), sa.ForeignKey("experiment.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_checklist_log_experiment_step", "checklist_log", ["experiment_id", "step"])


def downgrade() -> None:
    op.drop_index("ix_checklist_log_experiment_step", table_name="checklist_log")
    op.drop_column("checklist_log", "experiment_id")
    op.drop_column("experiment", "manual_checklist")
