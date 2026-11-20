"""library experiment follows pool: a library is in an experiment only through its pool

Revision ID: f3a91c5d7e20
Revises: e2b6f8a1c437
Create Date: 2026-11-20 12:00:00.000000

library.experiment_id duplicates pool.experiment_id and drifted: libraries removed from a pool
(remove-all, lab prep re-pooling, merging) kept the experiment, and libraries added to a pool already
in an experiment never got it. The data is synced to the pools first (not reversible), then:
- fk_library_pool_experiment: (pool_id, experiment_id) -> pool (id, experiment_id), ON UPDATE CASCADE,
  so a pooled library is in its pool's experiment or in none, and (un)linking a pool carries its libraries;
- ck_library_experiment_requires_pool: an unpooled library is in no experiment.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f3a91c5d7e20"
down_revision: Union[str, Sequence[str], None] = "e2b6f8a1c437"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE library SET experiment_id = NULL WHERE pool_id IS NULL AND experiment_id IS NOT NULL")
    op.execute(
        "UPDATE library SET experiment_id = pool.experiment_id FROM pool "
        "WHERE library.pool_id = pool.id AND library.experiment_id IS DISTINCT FROM pool.experiment_id"
    )

    op.create_unique_constraint("uq_pool_id_experiment_id", "pool", ["id", "experiment_id"])
    op.create_foreign_key(
        "fk_library_pool_experiment", "library", "pool",
        ["pool_id", "experiment_id"], ["id", "experiment_id"], onupdate="CASCADE",
    )
    op.create_check_constraint(
        "ck_library_experiment_requires_pool", "library", "experiment_id IS NULL OR pool_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_library_experiment_requires_pool", "library", type_="check")
    op.drop_constraint("fk_library_pool_experiment", "library", type_="foreignkey")
    op.drop_constraint("uq_pool_id_experiment_id", "pool", type_="unique")
