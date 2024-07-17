import math
from typing import Optional

import sqlalchemy as sa

from ...categories import IndexTypeEnum
from ... import models, PAGE_LIMIT
from .. import exceptions


def create_index_kit(
    self, name: str,
    type: IndexTypeEnum,
) -> models.IndexKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(models.IndexKit).where(models.IndexKit.name == name).first():
        raise exceptions.NotUniqueValue(f"index_kit with name '{name}', already exists.")

    seq_kit = models.IndexKit(
        name=name.strip(),
        type_id=type.id
    )
    self._session.add(seq_kit)
    self._session.commit()
    self._session.refresh(seq_kit)

    if not persist_session:
        self.close_session()
    return seq_kit


def get_index_kit(self, id: int) -> Optional[models.IndexKit]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.IndexKit, id)

    if not persist_session:
        self.close_session()

    return res


def get_index_kit_by_name(self, name: str) -> Optional[models.IndexKit]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.IndexKit).where(models.IndexKit.name == name).first()

    if not persist_session:
        self.close_session()
    return res


def get_index_kits(
    self, limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = 0,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[models.IndexKit], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.IndexKit)

    n_pages = math.ceil(query.count() / limit) if limit is not None else 1

    if sort_by is not None:
        attr = getattr(models.IndexKit, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    if limit is not None:
        query = query.limit(limit)

    if offset is not None:
        query = query.offset(offset)

    res = query.all()

    if not persist_session:
        self.close_session()

    return res, n_pages


def query_index_kit(
    self, word: str, limit: Optional[int] = PAGE_LIMIT
) -> list[models.IndexKit]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.IndexKit)

    query = query.order_by(sa.func.similarity(models.IndexKit.name, word).desc())

    if limit is not None:
        query = query.limit(limit)

    res = query.all()

    if not persist_session:
        self.close_session()
    return res
