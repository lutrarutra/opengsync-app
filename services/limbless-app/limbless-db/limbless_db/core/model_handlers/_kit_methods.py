import math
import string
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..DBHandler import DBHandler

import sqlalchemy as sa
from ...categories import KitTypeEnum, KitType
from ... import PAGE_LIMIT, models


def create_kit(
    self: "DBHandler",
    name: str,
    identifier: str,
    kit_type: KitTypeEnum,
) -> models.Kit:
    if not (persist_session := self._session is not None):
        self.open_session()

    kit = models.Kit(
        name=name,
        identifier=identifier,
        kit_type_id=kit_type.id,
    )

    self.session.add(kit)
    self.session.commit()
    self.session.refresh(kit)

    if not persist_session:
        self.close_session()

    return kit


def get_kit(self: "DBHandler", id: int) -> Optional[models.Kit]:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.Kit, id)

    if not persist_session:
        self.close_session()

    return res


def get_kits(
    self: "DBHandler", limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = 0,
    sort_by: Optional[str] = None, descending: bool = False
) -> tuple[list[models.Kit], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Kit)

    if sort_by is not None:
        if sort_by not in models.Kit.sortable_fields:
            raise ValueError(f"Invalid sort_by field: {sort_by}")
        attr = getattr(models.Kit, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    n_pages = math.ceil(query.count() / limit) if limit is not None else 1

    if limit is not None:
        query = query.limit(limit)

    if offset is not None:
        query = query.offset(offset)

    res = query.all()

    if not persist_session:
        self.close_session()

    return res, n_pages