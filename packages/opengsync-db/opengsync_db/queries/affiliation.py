import sqlalchemy as sa

from ..models.links import UserAffiliation
from ..models import User, Group
from ..categories import AffiliationType
from ..core import utils


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


def search(
    user_name: str | None = None,
    group_name: str | None = None,
    user_name_weight: float = 0.5,
    group_name_weight: float = 0.5,
    statement: sa.Select[tuple[UserAffiliation]] = sa.select(UserAffiliation),
) -> sa.Select[tuple[UserAffiliation]]:
    filter_conditions: list[sa.ColumnElement[bool]] = []
    relevance = sa.literal(0.0)

    if user_name is not None:
        filter_conditions.append(utils.safe_trgm_search(User.name.expression, user_name))
        relevance += sa.func.similarity(User.name.expression, user_name) * user_name_weight

    if group_name is not None:
        filter_conditions.append(utils.safe_trgm_search(Group.name, group_name))
        relevance += sa.func.similarity(Group.name, group_name) * group_name_weight

    if not filter_conditions:
        return statement

    statement = statement.where(sa.or_(*filter_conditions))

    if user_name is not None:
        statement = statement.join(User, User.id == UserAffiliation.user_id)
    if group_name is not None:
        statement = statement.join(Group, Group.id == UserAffiliation.group_id)

    return statement.order_by(relevance.desc())


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