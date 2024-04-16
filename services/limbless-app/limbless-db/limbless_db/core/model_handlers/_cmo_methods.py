import math
from typing import Optional

from ... import models, PAGE_LIMIT


def create_cmo(
    self,
    sequence: str,
    pattern: str,
    read: str,
) -> models.CMO:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()
    
    cmo = models.CMO(
        sequence=sequence.strip(),
        pattern=pattern.strip(),
        read=read.strip(),
    )

    self._session.add(cmo)
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
    limit: Optional[int] = PAGE_LIMIT,
    offset: Optional[int] = None
) -> tuple[list[models.CMO], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.CMO)
    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    res = query.all()

    if not persist_session:
        self.close_session()
    return res, n_pages