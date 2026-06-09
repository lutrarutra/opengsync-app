import sqlalchemy as sa

from ..models import Lane, Experiment


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
    experiment: Experiment | None = None,
    search_experiment_name: str | None = None,
    statement: sa.Select[tuple[Lane]] = sa.select(Lane),
) -> sa.Select[tuple[Lane]]:
    if id is not None:
        statement = statement.where(Lane.id == id)
    if experiment_id is not None:
        statement = statement.where(Lane.experiment_id == experiment_id)
    if number is not None:
        statement = statement.where(Lane.number == number)
    if experiment is not None:
        statement = statement.where(Lane.experiment_id == experiment.id)
    if search_experiment_name is not None:
        statement = statement.join(Experiment, Lane.experiment_id == Experiment.id).order_by(sa.func.similarity(Experiment.name, search_experiment_name).desc())
    return statement