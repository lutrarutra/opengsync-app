import sqlalchemy as sa

from ..models import Experiment, User, Lane, Project, Sample, Library, links
from ..categories import ExperimentStatus, ExperimentWorkFlow
from ..core import utils



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


def search(
    name: str | None = None,
    operator_name: str | None = None,
    name_weight: float = 0.5,
    operator_name_weight: float = 0.5,
    statement: sa.Select[tuple[Experiment]] = sa.select(Experiment),
) -> sa.Select[tuple[Experiment]]:
    filter_conditions: list[sa.ColumnElement[bool]] = []
    relevance = sa.literal(0.0)

    if name is not None:
        filter_conditions.append(utils.safe_trgm_search(Experiment.name, name))
        relevance += sa.func.similarity(Experiment.name, name) * name_weight

    if operator_name is not None:
        full_name = User.name.expression
        filter_conditions.append(utils.safe_trgm_search(full_name, operator_name))
        relevance += sa.func.similarity(full_name, operator_name) * operator_name_weight

    if not filter_conditions:
        return statement

    statement = statement.where(sa.or_(*filter_conditions))

    if operator_name is not None:
        statement = statement.join(User, Experiment.operator_id == User.id)

    return statement.order_by(sa.nulls_last(relevance.desc()))


def select(
    id: int | None = None,
    name: str | None = None,
    status: ExperimentStatus | None = None,
    project_id: int | None = None,
    status_in: list[ExperimentStatus] | None = None,
    workflow_in: list[ExperimentWorkFlow] | None = None,
    statement: sa.Select[tuple[Experiment]] = sa.select(Experiment),
) -> sa.Select[tuple[Experiment]]:
    return statement.where(*where_clauses(
        id=id, name=name, status=status, project_id=project_id,
        status_in=status_in, workflow_in=workflow_in,
    ))


def where_clauses(
    id: int | None = None,
    name: str | None = None,
    status: ExperimentStatus | None = None,
    project_id: int | None = None,
    status_in: list[ExperimentStatus] | None = None,
    workflow_in: list[ExperimentWorkFlow] | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering experiments.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(Experiment.id == id)
    if name is not None:
        clauses.append(Experiment.name == name)
    if status is not None:
        clauses.append(Experiment.status_id == status.id)
    if status_in is not None:
        clauses.append(Experiment.status_id.in_([s.id for s in status_in]))
    if workflow_in is not None:
        clauses.append(Experiment.workflow_id.in_([w.id for w in workflow_in]))
    if project_id is not None:
        clauses.append(
            sa.select(1).where(
                (Project.id == project_id) &
                (Sample.project_id == Project.id) &
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.experiment_id == Experiment.id)
            ).correlate_except(Project, Sample, links.SampleLibraryLink, Library).exists()
        )

    return clauses