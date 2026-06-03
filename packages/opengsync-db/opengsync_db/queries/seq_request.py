import sqlalchemy as sa
from sqlalchemy import sql

from ..models import User, SeqRequest, Group
from ..categories import SeqRequestStatus


def select(
    id: int | None = None,
    status: SeqRequestStatus | None = None,
    status_in: list[SeqRequestStatus] | None = None,
    requestor: User | None = None,
    group: Group | None = None,
    statement: sql.Select[tuple[SeqRequest]] = sa.select(SeqRequest),
) -> sql.Select[tuple[SeqRequest]]:
    if id is not None:
        statement = statement.where(SeqRequest.id == id)
    if status is not None:
        statement = statement.where(SeqRequest.status_id == status.id)
    if status_in is not None:
        statement = statement.where(SeqRequest.status_id.in_([s.id for s in status_in]))
    if requestor is not None:
        statement = statement.where(SeqRequest.requestor_id == requestor.id)
    if group is not None:
        statement = statement.where(SeqRequest.group_id == group.id)
    return statement