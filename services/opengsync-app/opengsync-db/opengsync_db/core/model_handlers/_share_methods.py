from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ..DBHandler import DBHandler

from ... import models, PAGE_LIMIT


def create_share_token(
    self: "DBHandler",
    owner: models.User,
    time_valid_min: int,
    paths: list[str],
    flush: bool = True,
) -> models.ShareToken:
    if not (persist_session := self._session is not None):
        self.open_session()

    token = models.ShareToken(
        owner=owner,
        time_valid_min=time_valid_min,
    )

    for path in paths:
        token.paths.append(models.SharePath(path=path))

    self.session.add(token)

    if flush:
        self.flush()

    if not persist_session:
        self.close_session()

    return token


def get_share_token(self: "DBHandler", uuid: str) -> models.ShareToken | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    token = self.session.get(models.ShareToken, uuid)

    if not persist_session:
        self.close_session()

    return token


def get_share_tokens(
    self: "DBHandler",
    owner: models.User | None = None,
    limit: int = PAGE_LIMIT,
) -> list[models.ShareToken]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.ShareToken)

    if owner is not None:
        query = query.filter(models.ShareToken.owner_id == owner.id)

    if limit is not None:
        query = query.limit(limit)

    tokens = query.all()

    if not persist_session:
        self.close_session()

    return tokens