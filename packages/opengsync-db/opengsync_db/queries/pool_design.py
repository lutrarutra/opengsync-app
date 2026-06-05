import sqlalchemy as sa

from ..models import PoolDesign, FlowCellDesign
from ..categories import TaskStatus


def create(
    name: str,
    cycles_r1: int,
    cycles_i1: int,
    cycles_i2: int,
    cycles_r2: int,
    num_m_requested_reads: float | None,
) -> PoolDesign:
    return PoolDesign(
        name=name,
        cycles_r1=cycles_r1,
        cycles_i1=cycles_i1,
        cycles_r2=cycles_r2,
        cycles_i2=cycles_i2,
        num_m_requested_reads=num_m_requested_reads,
    )


def select(
    id: int | None = None,
    flow_cell_design_id: int | None = None,
    orphan: bool | None = None,
    archived: bool | None = None,
    statement: sa.Select[tuple[PoolDesign]] = sa.select(PoolDesign),
) -> sa.Select[tuple[PoolDesign]]:
    if id is not None:
        statement = statement.where(PoolDesign.id == id)

    if flow_cell_design_id is not None:
        statement = statement.where(
            PoolDesign.flow_cell_design_id == flow_cell_design_id
        )

    if orphan is not None:
        if orphan:
            statement = statement.where(
                PoolDesign.flow_cell_design_id.is_(None)
            )
        else:
            statement = statement.where(
                PoolDesign.flow_cell_design_id.is_not(None)
            )

    if archived is not None:
        if archived:
            statement = statement.where(
                sa.exists().where(
                    (PoolDesign.flow_cell_design_id == FlowCellDesign.id) &
                    (FlowCellDesign.task_status_id >= TaskStatus.COMPLETED.id)
                )
            )
        else:
            statement = statement.where(
                sa.exists().where(
                    (PoolDesign.flow_cell_design_id == FlowCellDesign.id) &
                    (FlowCellDesign.task_status_id < TaskStatus.COMPLETED.id)
                )
            )

    return statement