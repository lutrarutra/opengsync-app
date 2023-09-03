from typing import Optional, Union

from sqlalchemy.orm import selectinload

from ... import models
from .. import exceptions
from ...tools import SearchResult

def create_indexkit(
    self,
    name: str,
    commit: bool = True
) -> models.IndexKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(models.IndexKit).where(models.IndexKit.name == name).first():
        raise exceptions.ElementAlreadyExists(f"IndexKit with name '{name}', already exists.")

    seq_kit = models.IndexKit(
        name=name
    )

    self._session.add(seq_kit)
    if commit:
        self._session.commit()
        self._session.refresh(seq_kit)

    if not persist_session: self.close_session()
    return seq_kit

def get_indexkit(self, id: int) -> models.IndexKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.IndexKit).where(models.IndexKit.id == id).first()
    if not persist_session: self.close_session()
    return res

def get_indexkit_by_name(self, name: str) -> models.IndexKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.IndexKit).where(models.IndexKit.name == name).first()
    if not persist_session: self.close_session()
    return res
    
def query_indexkit(
    self, query: str, limit: Optional[int] = 20
) -> list[SearchResult]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()
    res = self._session.query(models.IndexKit).where(
        models.IndexKit.name.contains(query)
    )
    if limit is not None:
        res = res.limit(limit)

    res = res.all()

    res = [SearchResult(index_kit.id, str(index_kit)) for index_kit in res]
    
    if not persist_session: self.close_session()
    return res