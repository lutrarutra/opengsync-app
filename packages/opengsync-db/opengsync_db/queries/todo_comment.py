import sqlalchemy as sa

from ..models import TODOComment


def create(
    text: str,
    author,
    status=None,
    flow_cell_design_id: int | None = None,
    pool_design_id: int | None = None,
) -> TODOComment:
    return TODOComment(
        text=text.strip(),
        author=author,
        task_status_id=status.id if status is not None else None,
        flow_cell_design_id=flow_cell_design_id,
        pool_design_id=pool_design_id,
    )


def select(
    id: int | None = None,
    statement: sa.Select[tuple[TODOComment]] = sa.select(TODOComment),
) -> sa.Select[tuple[TODOComment]]:
    if id is not None:
        statement = statement.where(TODOComment.id == id)
    return statement
