import sqlalchemy as sa

from ..models import SeqRun, Experiment
from ..categories import RunStatus, ReadType, ExperimentStatus
from ..core.units import Quantity
from ..core import utils


def create(
    experiment_name: str, status: RunStatus, instrument_name: str,
    run_folder: str, flowcell_id: str, read_type: ReadType,
    r1_cycles: int | None, i1_cycles: int | None, r2_cycles: int | None, i2_cycles: int | None,
    quantities: dict[str, "Quantity"] | None = None, rta_version: str | None = None, recipe_version: str | None = None,
    side: str | None = None, flowcell_mode: str | None = None,
) -> SeqRun:
    run = SeqRun(
        experiment_name=experiment_name.strip(),
        status_id=status.id,
        instrument_name=instrument_name.strip(),
        run_folder=run_folder.strip(),
        flowcell_id=flowcell_id.strip(),
        read_type_id=read_type.id,
        rta_version=rta_version.strip() if rta_version else None,
        recipe_version=recipe_version.strip() if recipe_version else None,
        side=side.strip() if side else None,
        flowcell_mode=flowcell_mode.strip() if flowcell_mode else None,
        r1_cycles=r1_cycles,
        r2_cycles=r2_cycles,
        i1_cycles=i1_cycles,
        i2_cycles=i2_cycles,
    )
    if quantities is not None:
        for key, value in quantities.items():
            run.set_quantity(key, value)
    return run


def search(
    experiment_name: str | None = None,
    run_folder: str | None = None,
    flow_cell_id: str | None = None,
    statement: sa.Select[tuple[SeqRun]] = sa.select(SeqRun),
) -> sa.Select[tuple[SeqRun]]:
    filter_conditions: list[sa.ColumnElement[bool]] = []

    if experiment_name is not None:
        filter_conditions.append(utils.safe_trgm_search(SeqRun.experiment_name, experiment_name))
    if run_folder is not None:
        filter_conditions.append(utils.safe_ilike(SeqRun.run_folder, run_folder))
    if flow_cell_id is not None:
        filter_conditions.append(utils.safe_ilike(SeqRun.flowcell_id, flow_cell_id))

    if not filter_conditions:
        return statement

    return (
        statement
        .where(sa.or_(*filter_conditions))
        .order_by(sa.nulls_last(
            sa.func.coalesce(
                *[sa.func.similarity(col, val) for col, val in filter(
                    lambda x: x[1] is not None,
                    [(SeqRun.experiment_name, experiment_name),
                     (SeqRun.run_folder, run_folder),
                     (SeqRun.flowcell_id, flow_cell_id)]
                )]
            ).desc()
        ))
    )


def select(
    id: int | None = None,
    experiment_name: str | None = None,
    status: RunStatus | None = None,
    status_in: list[RunStatus] | None = None,
    experiment_status: ExperimentStatus | None = None,
    experiment_status_in: list[ExperimentStatus] | None = None,
    statement: sa.Select[tuple[SeqRun]] = sa.select(SeqRun),
) -> sa.Select[tuple[SeqRun]]:
    if id is not None:
        statement = statement.where(SeqRun.id == id)
    if status is not None:
        statement = statement.where(SeqRun.status_id == status.id)
    if status_in is not None:
        statement = statement.where(SeqRun.status_id.in_([s.id for s in status_in]))
    if experiment_name is not None:
        statement = statement.where(SeqRun.experiment_name == experiment_name)

    if experiment_status is not None or experiment_status_in is not None:
        statement = statement.join(
            Experiment,
            Experiment.name == SeqRun.experiment_name,
        )

        if experiment_status is not None:
            statement = statement.where(Experiment.status_id == experiment_status.id)
            
        if experiment_status_in is not None:
            statement = statement.where(Experiment.status_id.in_([s.id for s in experiment_status_in]))

    return statement