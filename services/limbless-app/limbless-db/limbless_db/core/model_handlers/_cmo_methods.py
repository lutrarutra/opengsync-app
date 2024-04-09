import math
from typing import Optional

from ... import models, PAGE_LIMIT
from .. import exceptions


def create_cmo(
    self,
    sequence: str,
    pattern: str,
    read: str,
    sample_id: int,
    library_id: int,
    commit: bool = True
) -> models.CMO:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id '{sample_id}', not found.")

    if (_ := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id '{library_id}', not found.")
    
    cmo = models.CMO(
        sequence=sequence.strip(),
        pattern=pattern.strip(),
        read=read.strip(),
        sample_id=sample_id,
        library_id=library_id
    )

    self._session.add(cmo)
    
    if commit:
        self._session.commit()
        self._session.refresh(cmo)

    if not persist_session:
        self.close_session()
    return cmo


def get_cmo(self, cmo_id: int) -> models.CMO:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.CMO, cmo_id)

    if not persist_session:
        self.close_session()
    return res


def get_cmos(
    self,
    sample_id: Optional[int] = None,
    library_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT,
    offset: Optional[int] = None
) -> tuple[list[models.CMO], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.CMO)
    if sample_id is not None:
        query = query.filter(models.CMO.sample_id == sample_id)
    if library_id is not None:
        query = query.filter(models.CMO.library_id == library_id)

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    res = query.all()

    if not persist_session:
        self.close_session()
    return res, n_pages