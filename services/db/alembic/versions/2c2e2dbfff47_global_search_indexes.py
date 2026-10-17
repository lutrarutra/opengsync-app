"""trigram indexes for the navbar global search

Revision ID: 2c2e2dbfff47
Revises: d2f6a8b3c1e7
Create Date: 2026-10-12 14:00:00.000000

Sample names had no trigram index. The *_compact_idx indexes cover separator-insensitive matching
("scrnaseq01" finds "scRNA_seq-01"); their expression must stay identical to
opengsync_db.core.utils.compact_key or Postgres will not use them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2c2e2dbfff47"
down_revision: Union[str, Sequence[str], None] = "d2f6a8b3c1e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (index name, table, column)
COMPACT_INDEXES = (
    ("trgm_library_name_compact_idx", "library", "name"),
    ("trgm_library_sample_name_compact_idx", "library", "sample_name"),
    ("trgm_sample_name_compact_idx", "sample", "name"),
    ("trgm_pool_name_compact_idx", "pool", "name"),
    ("trgm_experiment_name_compact_idx", "experiment", "name"),
    ("trgm_lab_prep_name_compact_idx", "lab_prep", "name"),
)


def upgrade() -> None:
    op.create_index(
        "trgm_sample_name_idx", "sample",
        [sa.literal_column("lower(name) gin_trgm_ops")], unique=False, postgresql_using="gin",
    )
    for name, table, column in COMPACT_INDEXES:
        op.create_index(
            name, table,
            [sa.literal_column(f"regexp_replace(lower({column}), '[^a-z0-9]+', '', 'g') gin_trgm_ops")],
            unique=False, postgresql_using="gin",
        )


def downgrade() -> None:
    for name, table, _ in COMPACT_INDEXES:
        op.drop_index(name, table_name=table, postgresql_using="gin")
    op.drop_index("trgm_sample_name_idx", table_name="sample", postgresql_using="gin")
