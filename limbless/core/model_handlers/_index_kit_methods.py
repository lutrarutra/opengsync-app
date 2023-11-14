import math
from typing import Optional, Union

from sqlmodel import func, and_
import pandas as pd

from ... import models, logger, PAGE_LIMIT
from .. import exceptions
from ...categories import LibraryType


def create_index_kit(
    self, name: str
) -> models.IndexKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(models.IndexKit).where(models.IndexKit.name == name).first():
        raise exceptions.NotUniqueValue(f"index_kit with name '{name}', already exists.")

    seq_kit = models.IndexKit(
        name=name
    )
    self._session.add(seq_kit)
    self._session.commit()
    self._session.refresh(seq_kit)

    if not persist_session:
        self.close_session()
    return seq_kit


def get_index_kit(self, id: int) -> models.IndexKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.IndexKit, id)

    if not persist_session:
        self.close_session()

    return res


def get_index_kit_by_name(self, name: str) -> models.IndexKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.IndexKit).where(models.IndexKit.name == name).first()
    if not persist_session:
        self.close_session()
    return res


def get_num_index_kits(self) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.IndexKit).count()
    if not persist_session:
        self.close_session()
    return res


def get_index_kits(
    self, limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = 0
) -> tuple[list[models.IndexKit], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.IndexKit).order_by(models.IndexKit.id.desc())

    n_pages = math.ceil(query.count() / limit) if limit is not None else 1

    if limit is not None:
        query = query.limit(limit)

    if offset is not None:
        query = query.offset(offset)

    res = query.all()

    if not persist_session:
        self.close_session()

    return res, n_pages


def query_index_kit(
    self, word: str, library_type: Optional[LibraryType] = None, limit: Optional[int] = PAGE_LIMIT
) -> list[models.IndexKit]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.IndexKit)

    if library_type is not None:
        query = query.join(
            models.IndexKitLibraryType,
            and_(
                models.IndexKitLibraryType.index_kit_id == models.IndexKit.id,
                models.IndexKitLibraryType.library_type_id == library_type.value.id
            )
        )

    query = query.order_by(func.similarity(models.IndexKit.name, word).desc())

    if limit is not None:
        query = query.limit(limit)

    res = query.all()

    if not persist_session:
        self.close_session()
    return res
