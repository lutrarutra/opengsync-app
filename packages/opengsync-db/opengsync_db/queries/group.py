import sqlalchemy as sa

from ..models import Group, User, links
from ..categories import GroupType


def create(
    name: str, type: GroupType
) -> Group:
    return Group(
        name=name.strip(),
        type_id=type.id
    )


def select(
    id: int | None = None,
    user: User | None = None,
    type: GroupType | None = None,
    search_name: str | None = None,
    type_in: list[GroupType] | None = None,
    statement: sa.Select[tuple[Group]] = sa.select(Group),
) -> sa.Select[tuple[Group]]:
    if id is not None:
        statement = statement.where(Group.id == id)
    if user is not None:
        statement = statement.where(
            sa.exists().where(
                (links.UserAffiliation.user_id == user.id) &
                (links.UserAffiliation.group_id == Group.id)
            )
        )
    if type is not None:
        statement = statement.where(Group.type_id == type.id)
    if type_in is not None:
        statement = statement.where(Group.type_id.in_([t.id for t in type_in]))
    if search_name is not None:
        statement = statement.where(sa.nulls_last(sa.func.similarity(Group.name, search_name).desc()))
    return statement