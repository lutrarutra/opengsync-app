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
    if id is not None:
        statement = statement.where(DataPath.id == id)
    if path is not None:
        statement = statement.where(DataPath.path == path)

    if type is not None:
        statement = statement.where(DataPath.type_id == type.id)

    if type_in is not None:
        statement = statement.where(DataPath.type_id.in_([t.id for t in type_in]))

    if project_id is not None:
        statement = statement.where(DataPath.project_id == project_id)

    if seq_request_id is not None:
        statement = statement.where(DataPath.seq_request_id == seq_request_id)

    if library_id is not None:
        statement = statement.where(DataPath.library_id == library_id)

    if experiment_id is not None:
        statement = statement.where(DataPath.experiment_id == experiment_id)
    
    return statement