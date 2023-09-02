from typing import Optional, Union

from sqlalchemy.orm import selectinload

from ... import models
from .. import exceptions

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

    seq_kit = self._session.get(models.SeqKit, seq_kit_id)
    if not seq_kit:
        raise exceptions.ElementDoesNotExist(f"SeqKit with id '{seq_kit_id}', not found.")

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

    if not persist_session: self.close_session()
    return seq_index

def get_seqindex(self, id: int) -> models.SeqIndex:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqIndex).where(models.SeqIndex.id == id).first()
    if not persist_session: self.close_session()
    return res

def get_seqindices_by_adapter(self, adapter: str) -> list[models.SeqIndex]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqIndex).where(models.SeqIndex.adapter == adapter).all()
    if not persist_session: self.close_session()
    return res