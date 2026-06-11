import sqlalchemy as sa

from ..models import DataPath, Project, SeqRequest, Library, Experiment
from ..categories import DataPathType


def create(
    path: str,
    type: DataPathType,
    project: Project | None = None,
    seq_request: SeqRequest | None = None,
    library: Library | None = None,
    experiment: Experiment | None = None,
) -> DataPath:
    return DataPath(
        path=path,
        type_id=type.id,
        project=project,
        seq_request=seq_request,
        library=library,
        experiment=experiment,
    )


def select(
    id: int | None = None,
    path: str | None = None,
    type: DataPathType | None = None,
    type_in: list[DataPathType] | None = None,
    project_id: int | None = None,
    seq_request_id: int | None = None,
    library_id: int | None = None,
    experiment_id: int | None = None,
    statement: sa.Select[tuple[DataPath]] = sa.select(DataPath),
) -> sa.Select[tuple[DataPath]]:
    statement = statement.where(*where_clauses(
        id=id, path=path, type=type, type_in=type_in,
        project_id=project_id, seq_request_id=seq_request_id,
        library_id=library_id, experiment_id=experiment_id,
    ))
    return statement


def where_clauses(
    id: int | None = None,
    path: str | None = None,
    type: DataPathType | None = None,
    type_in: list[DataPathType] | None = None,
    project_id: int | None = None,
    seq_request_id: int | None = None,
    library_id: int | None = None,
    experiment_id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering data paths.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(DataPath.id == id)
    if path is not None:
        clauses.append(DataPath.path == path)
    if type is not None:
        clauses.append(DataPath.type_id == type.id)
    if type_in is not None:
        clauses.append(DataPath.type_id.in_([t.id for t in type_in]))
    if project_id is not None:
        clauses.append(DataPath.project_id == project_id)
    if seq_request_id is not None:
        clauses.append(DataPath.seq_request_id == seq_request_id)
    if library_id is not None:
        clauses.append(DataPath.library_id == library_id)
    if experiment_id is not None:
        clauses.append(DataPath.experiment_id == experiment_id)

    return clauses