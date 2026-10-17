"""checklist log: who checked or unchecked which checklist step, and when

Revision ID: a3f9c2e7b614
Revises: d5a7c3e9f142
Create Date: 2026-10-17 12:00:00.000000

Manual checks of the request review checklist were only stored as booleans in
seq_request.review_checklist. Checks before this migration have no history.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a3f9c2e7b614"
down_revision: Union[str, Sequence[str], None] = "d5a7c3e9f142"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "checklist_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("checklist_type_id", sa.SmallInteger(), nullable=False),
        sa.Column("step", sa.String(64), nullable=False),
        sa.Column("checked", sa.Boolean(), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()")),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("lims_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("seq_request_id", sa.Integer(), sa.ForeignKey("seq_request.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_checklist_log_seq_request_step", "checklist_log", ["seq_request_id", "step"])


def downgrade() -> None:
    op.drop_index("ix_checklist_log_seq_request_step", table_name="checklist_log")
    op.drop_table("checklist_log")
