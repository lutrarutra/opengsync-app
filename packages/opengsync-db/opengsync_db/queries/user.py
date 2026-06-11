import sqlalchemy as sa
from sqlalchemy import sql

from ..models import User, Group, links
from ..categories import UserRole

def create(
    email: str,
    hashed_password: str,
    first_name: str,
    last_name: str,
    role: UserRole,
) -> User:
    user = User(
        email=email.strip().lower(),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        password=hashed_password,
        role_id=role.id,
    )
    return user

def select(
    id: int | None = None,
    email: str | None = None,
    group: Group | None = None,
    role: UserRole | None = None,
    role_in: list[UserRole] | None = None,
    search_name: str | None = None,
    insider: bool | None = None,
    statement: sql.Select[tuple[User]] = sa.select(User),
) -> sa.Select[tuple[User]]:
    statement = statement.where(*where_clauses(
        id=id, email=email, role=role, role_in=role_in, insider=insider,
    ))
    if group is not None:
        statement = statement.join(links.UserAffiliation, links.UserAffiliation.user_id == User.id).where(links.UserAffiliation.group_id == group.id)
    if search_name is not None:
        statement = statement.order_by(
            sa.func.similarity(User.first_name + ' ' + User.last_name, search_name).desc()
        )
    return statement


def where_clauses(
    id: int | None = None,
    email: str | None = None,
    group: Group | None = None,
    role: UserRole | None = None,
    role_in: list[UserRole] | None = None,
    insider: bool | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering users.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(User.id == id)
    if email is not None:
        clauses.append(sa.func.lower(User.email) == email.lower())
    if role is not None:
        clauses.append(User.role_id == role.id)
    if role_in is not None:
        clauses.append(User.role_id.in_([r.id for r in role_in]))
    if insider is not None:
        if insider:
            clauses.append(User.role_id.in_([role.id for role in UserRole.insiders()]))
        else:
            clauses.append(User.role_id == UserRole.CLIENT.id)
    # Note: group filter requires a join, so it's not included here

    return clauses
    