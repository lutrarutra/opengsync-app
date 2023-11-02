import math
from typing import Optional

from sqlmodel import and_, func
import pandas as pd

from ... import models, logger, PAGE_LIMIT
from .. import exceptions
from ...tools import SearchResult


def create_seq_adapter(
    self, name: str, index_kit_id: int,
    commit: bool = True
) -> models.SeqAdapter:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (index_kit := self._session.get(models.IndexKit, index_kit_id)) is None:
        raise exceptions.ElementDoesNotExist(f"index_kit with id '{index_kit_id}', not found.")

    if get_adapter_by_name(self, index_kit_id, name) is not None:
        raise exceptions.NotUniqueValue(f"SeqAdapter with name '{name}', already exists in index-kit '{index_kit.name}'.")

    seq_adapter = models.SeqAdapter(
        name=name, index_kit_id=index_kit.id
    )

    self._session.add(seq_adapter)
    if commit:
        self._session.commit()
        self._session.refresh(seq_adapter)

    if not persist_session:
        self.close_session()
    return seq_adapter


def get_adapter(self, id: int) -> models.SeqAdapter:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.SeqAdapter, id)

    if not persist_session:
        self.close_session()
    return res


def get_adapters(
    self, index_kit_id: Optional[int] = None,
    offset: Optional[int] = None, limit: Optional[int] = PAGE_LIMIT,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[SearchResult], int]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.SeqAdapter)
    if index_kit_id is not None:
        query = query.where(
            models.SeqAdapter.index_kit_id == index_kit_id
        )

    if sort_by is not None:
        attr = getattr(models.SeqAdapter, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1
    
    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    res = query.all()

    if not persist_session:
        self.close_session()

    return res, n_pages


def get_num_adapters(
    self, index_kit_id: Optional[int] = None
) -> int:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.SeqAdapter)
    if index_kit_id is not None:
        query = query.where(
            models.SeqAdapter.index_kit_id == index_kit_id
        )

    res = query.count()

    if not persist_session:
        self.close_session()
    return res


def get_adapter_by_name(self, index_kit_id: int, name: str) -> models.SeqAdapter:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqAdapter).where(
        and_(
            models.SeqAdapter.name == name,
            models.SeqAdapter.index_kit_id == index_kit_id
        )
    ).first()

    if not persist_session:
        self.close_session()
    return res


def query_adapters(
    self, word: str, index_kit_id: Optional[int] = None,
    exclude_adapters_from_library_id: Optional[int] = None,  # TODO: exlcude adapters from library
    limit: Optional[int] = 10,
) -> list[SearchResult]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.SeqAdapter)
    if index_kit_id is not None:
        query = query.where(
            models.SeqAdapter.index_kit_id == index_kit_id
        )

    query = query.order_by(
        func.similarity(models.SeqAdapter.name, word).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    adapters = query.all()

    if not persist_session:
        self.close_session()

    return adapters