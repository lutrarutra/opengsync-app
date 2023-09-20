from typing import Optional

from sqlmodel import and_
import pandas as pd

from ... import models, logger
from .. import exceptions
from ...tools import SearchResult

from ._seq_adapter_methods import get_adapter_by_name, create_seq_adapter


def create_seq_index(
    self,
    sequence: str, adapter: str,
    type: str, index_kit_id: int,
    commit: bool = True
) -> models.SeqIndex:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (index_kit := self._session.get(models.index_kit, index_kit_id)) is None:
        raise exceptions.ElementDoesNotExist(f"index_kit with id '{index_kit_id}', not found.")

    if (seq_adapter := get_adapter_by_name(self, index_kit_id, adapter)) is None:
        seq_adapter = create_seq_adapter(self, adapter, index_kit_id, commit=True)

    if self._session.query(models.SeqIndex).where(
        and_(
            models.SeqIndex.sequence == sequence,
            models.SeqIndex.adapter_id == seq_adapter.id,
            models.SeqIndex.type == type,
            models.SeqIndex.index_kit_id == index_kit.id
        )
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"SeqIndex with sequence '{sequence}', already exists in index-kit '{index_kit.name}'.")

    seq_index = models.SeqIndex(
        sequence=sequence,
        adapter_id=seq_adapter.id,
        type=type,
        index_kit_id=index_kit.id
    )

    self._session.add(seq_index)
    if commit:
        self._session.commit()
        self._session.refresh(seq_index)

    if not persist_session:
        self.close_session()
    return seq_index


def get_seqindex(self, id: int) -> models.SeqIndex:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqIndex).where(models.SeqIndex.id == id).first()
    if not persist_session:
        self.close_session()
    return res


def get_seqindices(
    self, limit: Optional[int] = 20, offset: Optional[int] = None
) -> list[models.SeqIndex]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.SeqIndex).order_by(models.SeqIndex.id.desc())

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    indices = query.all()

    if not persist_session:
        self.close_session()

    return indices


def get_seqindices_by_adapter(self, adapter: str) -> list[models.SeqIndex]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqIndex).where(models.SeqIndex.adapter == adapter).all()
    if not persist_session:
        self.close_session()
    return res


def get_num_seqindices(self) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqIndex).count()
    if not persist_session:
        self.close_session()
    return res