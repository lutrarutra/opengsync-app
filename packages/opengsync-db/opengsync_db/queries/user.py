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
    if id is not None:
        statement = statement.where(User.id == id)
    if email is not None:
        statement = statement.where(sa.func.lower(User.email) == email.lower())
    if role is not None:
        statement = statement.where(User.role_id == role.id)
    if role_in is not None:
        statement = statement.where(User.role_id.in_([r.id for r in role_in]))
    if group is not None:
        statement = statement.join(links.UserAffiliation, links.UserAffiliation.user_id == User.id).where(links.UserAffiliation.group_id == group.id)
    if insider is not None:
        if insider:
            statement = statement.where(User.role_id.in_([role.id for role in UserRole.insiders()]))
        else:
            statement = statement.where(User.role_id == UserRole.CLIENT.id)
    if search_name is not None:
        statement = statement.order_by(
            sa.func.similarity(User.first_name + ' ' + User.last_name, search_name).desc()
        )
    return statement
    