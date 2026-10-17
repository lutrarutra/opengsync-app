import sqlalchemy as sa

from ..models import PoolDilution, Pool, Experiment


def select(
    id: int | None = None,
    pool_id: int | None = None,
    identifier: str | None = None,
    experiment_id: int | None = None,
    statement: sa.Select[tuple[PoolDilution]] = sa.select(PoolDilution),
) -> sa.Select[tuple[PoolDilution]]:
    if id is not None:
        statement = statement.where(PoolDilution.id == id)
    if pool_id is not None:
        statement = statement.where(PoolDilution.pool_id == pool_id)
    if experiment_id is not None:
        statement = statement.join(Pool, PoolDilution.pool_id == Pool.id).where(Pool.experiment_id == experiment_id)
    if identifier is not None:
        statement = statement.where(PoolDilution.identifier == identifier)
    return statement