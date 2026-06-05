import sqlalchemy as sa
from sqlalchemy import sql

from ..models import User, APIToken

def create(
    owner: User,
    time_valid_min: int,
) -> APIToken:
    return APIToken(
        owner=owner,
        time_valid_min=time_valid_min,
    )


def select(
    id: int | None = None,
    uuid: str | None = None,
    owner: User | None = None,
    statement: sql.Select[tuple[APIToken]] = sa.select(APIToken),
) -> sql.Select[tuple[APIToken]]:
    if id is not None:
        statement = statement.where(APIToken.id == id)
    if uuid is not None:
        statement = statement.where(APIToken.uuid == uuid)
    if owner is not None:
        statement = statement.where(APIToken.owner_id == owner.id)
    return statement