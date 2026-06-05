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
        task_status_id=task_status.id,
        flow_cell_type_id=flow_cell_type.id if flow_cell_type else None,
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
            FlowCellDesign.task_status_id == status.id
        )

    if status_in is not None:
        statement = statement.where(
            FlowCellDesign.task_status_id.in_([s.id for s in status_in])
        )

    if archived is not None:
        if archived:
            statement = statement.where(
                FlowCellDesign.task_status_id >= TaskStatus.COMPLETED.id
            )
        else:
            statement = statement.where(
                FlowCellDesign.task_status_id < TaskStatus.COMPLETED.id
            )

    return statement