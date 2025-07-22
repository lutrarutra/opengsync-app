import math
from typing import Optional, TYPE_CHECKING

from sqlalchemy.sql.operators import and_

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from .. import exceptions


def create_adapter(
    self: "DBHandler", index_kit_id: int,
    well: Optional[str] = None, flush: bool = True
) -> models.Adapter:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    if well is not None:
        if self.session.query(models.Adapter).where(
            and_(
                models.Adapter.well == well,
                models.Adapter.index_kit_id == index_kit_id
            )
        ).first():
            raise exceptions.NotUniqueValue(f"Adapter with plate_well '{well}', already exists.")

    adapter = models.Adapter(well=well, index_kit_id=index_kit_id,)
    self.session.add(adapter)

    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()

    return adapter


def get_adapter(self: "DBHandler", id: int) -> models.Adapter | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.Adapter, id)

    if not persist_session:
        self.close_session()

    return res


def get_adapters(
    self: "DBHandler", index_kit_id: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    count_pages: bool = False
) -> tuple[list[models.Adapter], int | None]:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Adapter)

    if index_kit_id is not None:
        query = query.where(models.Adapter.index_kit_id == index_kit_id)

    n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

    if sort_by is not None:
        attr = getattr(models.Adapter, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    if limit is not None:
        query = query.limit(limit)

    if offset is not None:
        query = query.offset(offset)

    res = query.all()

    if not persist_session:
        self.close_session()

    return res, n_pages