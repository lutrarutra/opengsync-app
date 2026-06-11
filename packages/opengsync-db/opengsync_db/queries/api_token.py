import sqlalchemy as sa
from sqlalchemy import sql

from ..models import User, APIToken

def create(
    owner: User,
    time_valid_min: int,
) -> APIToken:
    return APIToken(
        owner=owner,
        time_valid_min=time_valid_min,
    )


def select(
    id: int | None = None,
    uuid: str | None = None,
    owner: User | None = None,
    statement: sql.Select[tuple[APIToken]] = sa.select(APIToken),
) -> sql.Select[tuple[APIToken]]:
    statement = statement.where(*where_clauses(
        id=id, uuid=uuid,
        owner_id=owner.id if owner is not None else None,
    ))
    return statement


def where_clauses(
    id: int | None = None,
    uuid: str | None = None,
    owner_id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering API tokens.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(APIToken.id == id)
    if uuid is not None:
        clauses.append(APIToken.uuid == uuid)
    if owner_id is not None:
        clauses.append(APIToken.owner_id == owner_id)

    return clauses