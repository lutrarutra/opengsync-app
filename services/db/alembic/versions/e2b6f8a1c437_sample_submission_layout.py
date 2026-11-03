"""sample submission layout: how a request's samples, libraries or pools are placed in tubes or plate wells

Revision ID: e2b6f8a1c437
Revises: c4d7e9a2b815
Create Date: 2026-11-03 12:00:00.000000

Existing requests have no layout (submission_layout_type_id NULL).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e2b6f8a1c437"
down_revision: Union[str, Sequence[str], None] = "c4d7e9a2b815"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("seq_request", sa.Column("submission_layout_type_id", sa.SmallInteger(), nullable=True))
    op.create_table(
        "sample_submission_layout",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seq_request_id", sa.Integer(), sa.ForeignKey("seq_request.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sample_id", sa.Integer(), sa.ForeignKey("sample.id", ondelete="CASCADE"), nullable=True),
        sa.Column("library_id", sa.Integer(), sa.ForeignKey("library.id", ondelete="CASCADE"), nullable=True),
        sa.Column("pool_id", sa.Integer(), sa.ForeignKey("pool.id", ondelete="CASCADE"), nullable=True),
        sa.Column("set_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("position", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "(sample_id IS NOT NULL)::int + (library_id IS NOT NULL)::int + (pool_id IS NOT NULL)::int = 1",
            name="ck_sample_submission_layout_one_item",
        ),
        sa.UniqueConstraint("seq_request_id", "set_name", "position", name="uq_sample_submission_layout_position"),
    )
    op.create_index("ix_sample_submission_layout_seq_request_id", "sample_submission_layout", ["seq_request_id"])


def downgrade() -> None:
    op.drop_index("ix_sample_submission_layout_seq_request_id", table_name="sample_submission_layout")
    op.drop_table("sample_submission_layout")
    op.drop_column("seq_request", "submission_layout_type_id")
