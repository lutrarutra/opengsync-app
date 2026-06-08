import sqlalchemy as sa

from ..models.links import UserAffiliation


def select(
    user_id: int | None = None,
    group_id: int | None = None,
    statement: sa.Select[tuple[UserAffiliation]] = sa.select(UserAffiliation),
) -> sa.Select[tuple[UserAffiliation]]:
    if user_id is not None:
        statement = statement.where(UserAffiliation.user_id == user_id)
    if group_id is not None:
        statement = statement.where(UserAffiliation.group_id == group_id)
    return statement