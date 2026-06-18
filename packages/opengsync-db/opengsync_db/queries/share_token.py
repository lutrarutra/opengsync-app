import sqlalchemy as sa

from ..models import ShareToken, User, SharePath, Project


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


def select(
    uuid: str | None = None,
    owner: User | None = None,
    owner_id: int | None = None,
    project_id: int | None = None,
    statement: sa.Select[tuple[ShareToken]] = sa.select(ShareToken),
) -> sa.Select[tuple[ShareToken]]:
    statement = statement.where(*where_clauses(uuid=uuid, owner=owner, owner_id=owner_id))
    return statement


def where_clauses(
    uuid: str | None = None,
    owner: User | None = None,
    owner_id: int | None = None,
    project_id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering share tokens.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if uuid is not None:
        clauses.append(ShareToken.uuid == uuid)
    if owner is not None:
        clauses.append(ShareToken.owner_id == owner.id)
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