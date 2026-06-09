import sqlalchemy as sa

from ..models.links import UserAffiliation
from ..models import User, Group
from ..categories import AffiliationType


def create(
    user: User,
    group: Group,
    type: AffiliationType,
) -> UserAffiliation:
    return UserAffiliation(
        user_id=user.id,
        group_id=group.id,
        affiliation_type=type,
    )


def select(
    user_id: int | None = None,
    group_id: int | None = None,
    search_user_name: str | None = None,
    search_group_name: str | None = None,
    statement: sa.Select[tuple[UserAffiliation]] = sa.select(UserAffiliation),
) -> sa.Select[tuple[UserAffiliation]]:
    if user_id is not None:
        statement = statement.where(UserAffiliation.user_id == user_id)
    if group_id is not None:
        statement = statement.where(UserAffiliation.group_id == group_id)
    if search_user_name is not None:
        statement = statement.join(User, User.id == UserAffiliation.user_id).order_by(sa.func.similarity(User.name, search_user_name).desc())
    if search_group_name is not None:
        statement = statement.join(Group, Group.id == UserAffiliation.group_id).order_by(sa.func.similarity(Group.name, search_group_name).desc())
    return statement