from typing import Optional, Union

from sqlalchemy.orm import selectinload

from ... import models
from .. import exceptions

def create_seqkit(
    self,
    name: str,
    commit: bool = True
) -> models.SeqKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(models.SeqKit).where(models.SeqKit.name == name).first():
        raise exceptions.ElementAlreadyExists(f"SeqKit with name '{name}', already exists.")

    seq_kit = models.SeqKit(
        name=name
    )

    self._session.add(seq_kit)
    if commit:
        self._session.commit()
        self._session.refresh(seq_kit)

    if not persist_session: self.close_session()
    return seq_kit

def get_seqkit(self, id: int) -> models.SeqKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqKit).where(models.SeqKit.id == id).first()
    if not persist_session: self.close_session()
    return res

def get_seqkit_by_name(self, name: str) -> models.SeqKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqKit).where(models.SeqKit.name == name).first()
    if not persist_session: self.close_session()
    return res
    