import math
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
    kit_type: KitTypeEnum = KitType.LIBRARY_KIT,
    flush: bool = True
) -> models.Kit:
    if not (persist_session := self._session is not None):
        self.open_session()

    kit = models.Kit(
        name=name,
        identifier=identifier,
        kit_type_id=kit_type.id,
    )

    self.session.add(kit)

    if flush:
        self.flush()

    if not persist_session:
        self.close_session()

    return kit


def get_kit(self: "DBHandler", id: int | None = None, identifier: Optional[str] = None, name: Optional[str] = None) -> models.Kit | None:
    if id is None and identifier is None and name is None:
        raise ValueError("Either id or identifier must be provided.")

    if not (persist_session := self._session is not None):
        self.open_session()

    if id is not None:
        kit = self.session.get(models.Kit, id)
    elif identifier is not None:
        kit = self.session.query(models.Kit).where(models.Kit.identifier == identifier).first()
    else:
        kit = self.session.query(models.Kit).where(models.Kit.name == name).first()

    if not persist_session:
        self.close_session()

    return kit


def get_kit_by_name(self: "DBHandler", name: str) -> models.Kit | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    kit = self.session.query(models.Kit).where(models.Kit.name == name).first()

    if not persist_session:
        self.close_session()

    return kit


def get_kits(
    self: "DBHandler", limit: int | None = PAGE_LIMIT, offset: int | None = 0,
    sort_by: Optional[str] = None, descending: bool = False,
    count_pages: bool = False
) -> tuple[list[models.Kit], int | None]:
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

    n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

    if limit is not None:
        query = query.limit(limit)

    if offset is not None:
        query = query.offset(offset)

    res = query.all()

    if not persist_session:
        self.close_session()

    return res, n_pages


def query_kits(
    self: "DBHandler", word: str, limit: int | None = PAGE_LIMIT, kit_type: Optional[KitTypeEnum] = None,
) -> list[models.Kit]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Kit)

    if kit_type is not None:
        query = query.where(models.Kit.kit_type_id == kit_type.id)

    query = query.order_by(
        sa.func.similarity(models.Kit.identifier + ' ' + models.Kit.name, word).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    res = query.all()

    if not persist_session:
        self.close_session()
    return res


def update_kit(self, kit: models.Kit) -> models.Kit:
    if not (persist_session := self._session is not None):
        self.open_session()

    self.session.add(kit)

    if not persist_session:
        self.close_session()
    return kit


def delete_kit(self: "DBHandler", id: int, flush: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (kit := self.session.get(models.Kit, id)) is None:
        raise ValueError(f"Kit with id {id} not found.")

    self.session.delete(kit)

    if flush:
        self.flush()

    if not persist_session:
        self.close_session()