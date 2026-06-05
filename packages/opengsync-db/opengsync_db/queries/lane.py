import sqlalchemy as sa

from ..models import Lane


def create(
    number: int, experiment_id: int
) -> Lane:
    return Lane(
        number=number,
        experiment_id=experiment_id,
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