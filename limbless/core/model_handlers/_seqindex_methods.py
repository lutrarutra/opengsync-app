from typing import Optional

from sqlmodel import and_

from ... import models
from .. import exceptions
from ...tools import SearchResult


def create_seqindex(
    self,
    sequence: str,
    adapter: str,
    type: str,
    seq_kit_id: int,
    commit: bool = True
) -> models.SeqIndex:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    seq_kit = self._session.get(models.IndexKit, seq_kit_id)
    if not seq_kit:
        raise exceptions.ElementDoesNotExist(f"IndexKit with id '{seq_kit_id}', not found.")

    seq_index = models.SeqIndex(
        sequence=sequence,
        adapter=adapter,
        type=type,
        seq_kit_id=seq_kit.id
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


def query_adapters(
    self, query: str, index_kit_id: Optional[int] = None,
    limit: Optional[int] = 20,
) -> list[SearchResult]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if index_kit_id is None:
        res = self._session.query(models.SeqIndex.adapter).where(
            models.SeqIndex.adapter.contains(query)
        ).distinct()
    else:
        res = self._session.query(models.SeqIndex.adapter).where(
            and_(
                models.SeqIndex.adapter.contains(query),
                models.SeqIndex.seq_kit_id == index_kit_id
            )
        ).distinct()

    if limit is not None:
        res = res.limit(limit)

    res = res.all()

    res = [SearchResult(a[0], a[0]) for a in res]

    if not persist_session:
        self.close_session()
    return res


def get_adapters_from_kit(
    self, index_kit_id: int, limit: Optional[int] = None
) -> list[SearchResult]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqIndex.adapter).where(
        models.SeqIndex.seq_kit_id == index_kit_id
    ).distinct()

    if limit is not None:
        res = res.limit(limit)

    res = res.all()

    res = [SearchResult(a[0], a[0]) for a in res]

    if not persist_session:
        self.close_session()
    return res
