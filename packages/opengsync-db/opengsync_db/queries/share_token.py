import sqlalchemy as sa

from ..models import ShareToken, User, SharePath, Project
from ..core import utils


def create(
    owner: User,
    time_valid_min: int,
    paths: list[str],
) -> ShareToken:
    return ShareToken(
        owner=owner,
        time_valid_min=time_valid_min,
        paths=[SharePath(path=path) for path in paths],
    )


def search(
    uuid: str | None = None,
    owner_name: str | None = None,
    statement: sa.Select[tuple[ShareToken]] = sa.select(ShareToken),
) -> sa.Select[tuple[ShareToken]]:
    """Prefix match on the uuid, fuzzy search on the owner's full name."""
    if uuid is not None:
        statement = statement.where(ShareToken.uuid.startswith(uuid.strip().lower(), autoescape=True))
    if owner_name is not None:
        full_name = User.name.expression
        statement = statement.join(User, ShareToken.owner_id == User.id).where(
            utils.safe_trgm_search(full_name, owner_name)
        ).order_by(sa.func.similarity(full_name, owner_name).desc())
    return statement


def select(
    uuid: str | None = None,
    owner_id: int | None = None,
    project_id: int | None = None,
    statement: sa.Select[tuple[ShareToken]] = sa.select(ShareToken),
) -> sa.Select[tuple[ShareToken]]:
    statement = statement.where(*where_clauses(uuid=uuid, owner_id=owner_id, project_id=project_id))
    return statement


def where_clauses(
    uuid: str | None = None,
    owner_id: int | None = None,
    project_id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering share tokens.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if uuid is not None:
        clauses.append(ShareToken.uuid == uuid)
    if owner_id is not None:
        clauses.append(ShareToken.owner_id == owner_id)
    if project_id is not None:
        clauses.append(
            sa.select(1).where(
                (ShareToken.uuid == Project.share_token_uuid),
                (Project.id == project_id)
            ).correlate_except(Project).exists()
        )
    return clauses