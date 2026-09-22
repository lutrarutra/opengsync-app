"""set null ba_report on media_file delete

Revision ID: c3e8a91f4b20
Revises: db7f9caeaeef
Create Date: 2026-08-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3e8a91f4b20'
down_revision: Union[str, Sequence[str], None] = 'db7f9caeaeef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FK_SPECS = (
    ("library_ba_report_id_fkey", "library"),
    ("sample_ba_report_id_fkey", "sample"),
    ("pool_ba_report_id_fkey", "pool"),
    ("lane_ba_report_id_fkey", "lane"),
)


def upgrade() -> None:
    """Upgrade schema."""
    for name, table in _FK_SPECS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, "media_file", ["ba_report_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    """Downgrade schema."""
    for name, table in _FK_SPECS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, "media_file", ["ba_report_id"], ["id"])
