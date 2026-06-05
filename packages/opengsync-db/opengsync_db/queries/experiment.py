import sqlalchemy as sa

from ..models import Experiment, Project, links, Sample, Library, Lane, User
from ..categories import ExperimentStatus, ExperimentWorkFlow


def create(
    name: str,
    workflow: ExperimentWorkFlow,
    status: ExperimentStatus,
    sequencer_id: int,
    r1_cycles: int,
    i1_cycles: int,
    operator_id: int,
    r2_cycles: int | None = None,
    i2_cycles: int | None = None,
) -> Experiment:
    experiment = Experiment(
        name=name.strip(),
        sequencer_id=sequencer_id,
        workflow_id=workflow.id,
        r1_cycles=r1_cycles,
        r2_cycles=r2_cycles,
        i1_cycles=i1_cycles,
        i2_cycles=i2_cycles,
        status_id=status.id,
        operator_id=operator_id,
    )

    for lane_num in range(1, workflow.flow_cell_type.num_lanes + 1):
        experiment.lanes.append(Lane(number=lane_num))
    return experiment


def select(
    id: int | None = None,
    name: str | None = None,
    status: ExperimentStatus | None = None,
    project_id: int | None = None,
    status_in: list[ExperimentStatus] | None = None,
    workflow_in: list[ExperimentWorkFlow] | None = None,
    search_name: str | None = None,
    search_operator_name: str | None = None,
    statement: sa.Select[tuple[Experiment]] = sa.select(Experiment),
) -> sa.Select[tuple[Experiment]]:
    if id is not None:
        statement = statement.where(Experiment.id == id)
    if name is not None:
        statement = statement.where(Experiment.name == name)
    if status is not None:
        statement = statement.where(Experiment.status_id == status.id)
    if status_in is not None:
        statement = statement.where(Experiment.status_id.in_([s.id for s in status_in]))
    if workflow_in is not None:
        statement = statement.where(Experiment.workflow_id.in_([w.id for w in workflow_in]))
    if project_id is not None:
        statement = statement.where(
            sa.exists().where(
                (Project.id == project_id) &
                (Sample.project_id == Project.id) &
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.experiment_id == Experiment.id)
            )
        )

    if search_name is not None:
        statement = statement.order_by(sa.func.similarity(Experiment.name, search_name).desc())
    elif search_operator_name is not None:
        statement = statement.join(
            Experiment.operator
        ).order_by(
            sa.func.similarity(User.first_name + ' ' + User.last_name, search_operator_name).desc()
        )
    
    return statement