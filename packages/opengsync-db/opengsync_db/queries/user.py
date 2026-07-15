import sqlalchemy as sa
from sqlalchemy import sql

from ..models import User, links
from ..categories import UserRole, AccessLevel
from ..core import utils

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

def access_level(user_id: int) -> sql.ColumnElement[AccessLevel]:
    is_admin = sa.select(1).where(User.id == user_id, User.is_admin)
    is_insider = sa.select(1).where(User.id == user_id, User.is_insider)

    is_same_user = sa.select(1).where(User.id == user_id)

    return sa.case(
        (sa.exists(is_admin), AccessLevel.ADMIN),
        (sa.exists(is_insider), AccessLevel.INSIDER),
        (sa.exists(is_same_user), AccessLevel.WRITE),
        else_=AccessLevel.NONE
    )

def search(
    name: str | None = None,
    name_weight: float = 0.5,
    statement: sql.Select[tuple[User]] = sa.select(User),
) -> sql.Select[tuple[User]]:
    filter_conditions: list[sql.ColumnElement[bool]] = []
    relevance = sa.literal(0.0)

    if name is not None:
        full_name = User.name.expression
        filter_conditions.append(utils.safe_trgm_search(full_name, name))
        relevance += sa.func.similarity(full_name, name) * name_weight

    if not filter_conditions:
        return statement

    statement = statement.where(sa.or_(*filter_conditions))

    return statement.order_by(sa.nulls_last(relevance.desc()))


def select(
    id: int | None = None,
    email: str | None = None,
    group_id: int | None = None,
    role: UserRole | None = None,
    role_in: list[UserRole] | None = None,
    insider: bool | None = None,
    viewer_id: int | None = None,
    assignees_project_id: int | None = None,
    assignees_seq_request_id: int | None = None,
    statement: sql.Select[tuple[User]] = sa.select(User),
) -> sa.Select[tuple[User]]:
    return statement.where(*where_clauses(
        id=id, email=email, role=role, role_in=role_in, insider=insider,
        assignees_project_id=assignees_project_id,
        assignees_seq_request_id=assignees_seq_request_id,
        group_id=group_id, viewer_id=viewer_id
    ))


def where_clauses(
    id: int | None = None,
    email: str | None = None,
    group_id: int | None = None,
    role: UserRole | None = None,
    role_in: list[UserRole] | None = None,
    assignees_project_id: int | None = None,
    viewer_id: int | None = None,
    assignees_seq_request_id: int | None = None,
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

    if group_id is not None:
        clauses.append(sa.select(1).where(
            (links.UserAffiliation.user_id == User.id),
            (links.UserAffiliation.group_id == group_id)
        ).correlate_except(links.UserAffiliation).exists())
        
    if assignees_project_id is not None:
        clauses.append(sa.select(1).where(
            (links.ProjectAssigneeLink.user_id == User.id),
            (links.ProjectAssigneeLink.project_id == assignees_project_id)
        ).correlate_except(links.ProjectAssigneeLink).exists())

    if assignees_seq_request_id is not None:
        clauses.append(sa.select(1).where(
            (links.SeqRequestAssigneeLink.user_id == User.id),
            (links.SeqRequestAssigneeLink.seq_request_id == assignees_seq_request_id)
        ).correlate_except(links.SeqRequestAssigneeLink).exists())

    if viewer_id is not None:
        clauses.append(access_level(viewer_id) >= AccessLevel.READ)

    return clauses
    

def permissions(user_id: int, viewer_id: int) -> sa.Select[tuple[AccessLevel]]:
    return sa.select(access_level(viewer_id)).where(User.id == user_id)