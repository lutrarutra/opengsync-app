import sqlalchemy as sa

from ..models import Group, User, links
from ..categories import GroupType, AccessLevel, UserRole, AffiliationType
from ..core import utils


def create(
    name: str, type: GroupType
) -> Group:
    return Group(
        name=name.strip(),
        type_id=type.id
    )

def access_level(user_id: int) -> sa.ColumnElement[AccessLevel]:
    is_admin = sa.select(1).where(User.id == user_id, User.is_admin)
    is_insider = sa.select(1).where(User.id == user_id, User.is_insider)

    has_write_access = sa.select(1).where(
        (links.UserAffiliation.user_id == user_id) &
        (links.UserAffiliation.group_id == Group.id) &
        sa.or_(
            (links.UserAffiliation.affiliation_type_id == AffiliationType.OWNER.id),
            (links.UserAffiliation.affiliation_type_id == AffiliationType.MANAGER.id)
        )
    ).correlate_except(links.UserAffiliation)

    has_read_access = sa.select(1).where(
        (links.UserAffiliation.user_id == user_id) &
        (links.UserAffiliation.group_id == Group.id)
    ).correlate_except(links.UserAffiliation)

    return sa.case(
        (sa.exists(is_admin), AccessLevel.ADMIN),
        (sa.exists(is_insider), AccessLevel.INSIDER),
        (sa.exists(has_write_access), AccessLevel.WRITE),
        (sa.exists(has_read_access), AccessLevel.READ),
        else_=AccessLevel.NONE
    )

def search(
    name: str,
    statement: sa.Select[tuple[Group]] = sa.select(Group),
) -> sa.Select[tuple[Group]]:
    return statement.where(
        utils.safe_trgm_search(Group.name, name)
    ).order_by(sa.func.similarity(Group.name, name).desc())


def select(
    id: int | None = None,
    user_id: int | None = None,
    type: GroupType | None = None,
    name: str | None = None,
    type_in: list[GroupType] | None = None,
    statement: sa.Select[tuple[Group]] = sa.select(Group),
) -> sa.Select[tuple[Group]]:
    if id is not None:
        statement = statement.where(Group.id == id)
    if user_id is not None:
        statement = statement.where(
            sa.select(1).where(
                (links.UserAffiliation.user_id == user_id) &
                (links.UserAffiliation.group_id == Group.id)
            ).correlate_except(links.UserAffiliation).exists()
        )
    if name is not None:
        statement = statement.where(Group.name == name)
    if type is not None:
        statement = statement.where(Group.type_id == type.id)
    if type_in is not None:
        statement = statement.where(Group.type_id.in_([t.id for t in type_in]))
    return statement


def permissions(group_id: int, user_id: int) -> sa.Select[tuple[AccessLevel]]:
    return sa.select(access_level(user_id)).where(Group.id == group_id)