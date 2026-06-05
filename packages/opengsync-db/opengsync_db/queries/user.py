import sqlalchemy as sa
from sqlalchemy import sql

from ..models import User
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
    statement: sql.Select[tuple[User]] = sa.select(User),
) -> sa.Select[tuple[User]]:
    if id is not None:
        statement = statement.where(User.id == id)
    if email is not None:
        statement = statement.where(User.email == email)
    return statement
    