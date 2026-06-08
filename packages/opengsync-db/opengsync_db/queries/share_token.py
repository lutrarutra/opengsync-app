import sqlalchemy as sa

from ..models import ShareToken, User, SharePath


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
    statement: sa.Select[tuple[ShareToken]] = sa.select(ShareToken),
) -> sa.Select[tuple[ShareToken]]:
    if uuid is not None:
        statement = statement.where(ShareToken.uuid == uuid)
    if owner is not None:
        statement = statement.where(ShareToken.owner_id == owner.id)
    return statement