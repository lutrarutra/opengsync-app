import sqlalchemy as sa

from ..models import PoolDilution, Pool, Experiment


def select(
    id: int | None = None,
    pool: Pool | None = None,
    experiment: Experiment | None = None,
    statement: sa.Select[tuple[PoolDilution]] = sa.select(PoolDilution),
) -> sa.Select[tuple[PoolDilution]]:
    if id is not None:
        statement = statement.where(PoolDilution.id == id)
    if pool is not None:
        statement = statement.where(PoolDilution.pool_id == pool.id)
    if experiment is not None:
        statement = statement.join(Pool, PoolDilution.pool_id == Pool.id).where(Pool.experiment_id == experiment.id)
    return statement