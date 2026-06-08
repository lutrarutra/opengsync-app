import sqlalchemy as sa

from ..models import Group, User, links
from ..categories import GroupType, AccessLevel, UserRole, AffiliationType


def create(
    name: str, type: GroupType
) -> Group:
    return Group(
        name=name.strip(),
        type_id=type.id
    )

def access_level(user_id: int) -> sa.ColumnElement[AccessLevel]:
    is_admin = sa.select(1).where(
        User.id == user_id,
        User.role_id == UserRole.ADMIN.id
    )

    is_insider = sa.select(1).where(
        User.id == user_id,
        User.role_id.isin([UserRole.BIOINFORMATICIAN.id, UserRole.TECHNICIAN.id])
    )

    has_write_access = sa.select(1).where(
        sa.exists().where(
            (links.UserAffiliation.user_id == user_id) &
            (links.UserAffiliation.group_id == Group.id) &
            sa.or_(
                (links.UserAffiliation.affiliation_type_id == AffiliationType.OWNER.id),
                (links.UserAffiliation.affiliation_type_id == AffiliationType.MANAGER.id)
            )
        )
    )

    has_read_access = sa.select(1).where(
        sa.exists().where(
            (links.UserAffiliation.user_id == user_id) &
            (links.UserAffiliation.group_id == Group.id)
        )
    )

    return sa.case(
        (sa.exists(is_admin), AccessLevel.ADMIN),
        (sa.exists(is_insider), AccessLevel.INSIDER),
        (sa.exists(has_write_access), AccessLevel.WRITE),
        (sa.exists(has_read_access), AccessLevel.READ),
        else_=AccessLevel.NONE
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


def permissions(group_id: int, user_id: int) -> sa.Select[tuple[AccessLevel]]:
    return sa.select(access_level(user_id)).where(Group.id == group_id)