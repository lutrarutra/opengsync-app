from typing import Optional, Union

from sqlmodel import func, and_
import pandas as pd

from ... import models, logger
from .. import exceptions
from ...tools import SearchResult
from ...categories import LibraryType
from ._link_methods import link_index_kit_library_type


def create_index_kit(
    self, name: str, allowed_library_types: list[LibraryType]
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

    for library_type in allowed_library_types:
        link_index_kit_library_type(self, seq_kit.id, library_type.value.id)

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
    self, limit: Optional[int] = 20, offset: Optional[int] = 0
) -> list[models.IndexKit]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.IndexKit).order_by(models.IndexKit.id.desc())

    if limit is not None:
        query = query.limit(limit)

    if offset is not None:
        query = query.offset(offset)

    res = query.all()

    for index_kit in res:
        index_kit._num_adapters = self._session.query(models.SeqAdapter).where(
            models.SeqAdapter.index_kit_id == index_kit.id
        ).count()

    if not persist_session:
        self.close_session()

    return res


def query_index_kit(
    self, word: str, library_type: Optional[LibraryType] = None, limit: Optional[int] = 20
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
