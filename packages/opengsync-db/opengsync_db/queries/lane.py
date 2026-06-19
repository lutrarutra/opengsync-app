import sqlalchemy as sa

from ..models import Lane, Experiment
from ..core import utils


def create(
    number: int, experiment_id: int
) -> Lane:
    return Lane(
        number=number,
        experiment_id=experiment_id,
    )


def search(
    experiment_name: str | None = None,
    statement: sa.Select[tuple[Lane]] = sa.select(Lane),
) -> sa.Select[tuple[Lane]]:
    if experiment_name is None:
        return statement
    return (
        statement
        .join(Experiment, Lane.experiment_id == Experiment.id)
        .where(utils.safe_trgm_search(Experiment.name, experiment_name))
        .order_by(sa.nulls_last(sa.func.similarity(Experiment.name, experiment_name).desc()))
    )


def select(
    id: int | None = None,
    number: int | None = None,
    experiment_id: int | None = None,
    statement: sa.Select[tuple[Lane]] = sa.select(Lane),
) -> sa.Select[tuple[Lane]]:
    if id is not None:
        statement = statement.where(Lane.id == id)
    if experiment_id is not None:
        statement = statement.where(Lane.experiment_id == experiment_id)
    if number is not None:
        statement = statement.where(Lane.number == number)
    return statement