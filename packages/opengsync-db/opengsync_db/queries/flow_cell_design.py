import sqlalchemy as sa

from ..models import FlowCellDesign
from ..categories import TaskStatus, FlowCellType


def create(
    name: str,
    task_status: TaskStatus = TaskStatus.DRAFT,
    flow_cell_type: FlowCellType | None = None,
) -> FlowCellDesign:
    return FlowCellDesign(
        name=name,
        task_status=task_status,
        stored_flow_cell_type=flow_cell_type,
    )


def select(
    id: int | None = None,
    status: TaskStatus | None = None,
    status_in: list[TaskStatus] | None = None,
    archived: bool | None = None,
    statement: sa.Select[tuple[FlowCellDesign]] = sa.select(FlowCellDesign),
) -> sa.Select[tuple[FlowCellDesign]]:
    if id is not None:
        statement = statement.where(FlowCellDesign.id == id)

    if status is not None:
        statement = statement.where(
            FlowCellDesign.task_status == status
        )

    if status_in is not None:
        statement = statement.where(
            FlowCellDesign.task_status.in_(status_in)
        )

    if archived is not None:
        if archived:
            statement = statement.where(
                FlowCellDesign.task_status >= TaskStatus.COMPLETED
            )
        else:
            statement = statement.where(
                FlowCellDesign.task_status < TaskStatus.COMPLETED
            )

    return statement