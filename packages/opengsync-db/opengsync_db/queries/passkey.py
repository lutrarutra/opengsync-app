import sqlalchemy as sa
from sqlalchemy import sql

from ..models import User, UserPasskey


def create(
    user: User,
    credential_id: bytes,
    public_key: bytes,
    sign_count: int,
    name: str,
    transports: list[str] | None = None,
    aaguid: str | None = None,
    backed_up: bool = False,
) -> UserPasskey:
    return UserPasskey(
        user=user,
        credential_id=credential_id,
        public_key=public_key,
        sign_count=sign_count,
        name=name[:64],
        transports=",".join(transports) if transports else None,
        aaguid=aaguid,
        backed_up=backed_up,
    )


def select(
    id: int | None = None,
    user_id: int | None = None,
    credential_id: bytes | None = None,
    statement: sql.Select[tuple[UserPasskey]] = sa.select(UserPasskey),
) -> sql.Select[tuple[UserPasskey]]:
    statement = statement.where(*where_clauses(
        id=id, user_id=user_id, credential_id=credential_id,
    ))
    return statement


def delete_all(user_id: int) -> sql.Delete:
    return sa.delete(UserPasskey).where(UserPasskey.user_id == user_id)


def where_clauses(
    id: int | None = None,
    user_id: int | None = None,
    credential_id: bytes | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering passkeys.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(UserPasskey.id == id)
    if user_id is not None:
        clauses.append(UserPasskey.user_id == user_id)
    if credential_id is not None:
        clauses.append(UserPasskey.credential_id == credential_id)

    return clauses
