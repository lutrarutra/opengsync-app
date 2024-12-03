import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from ...categories import BarcodeTypeEnum
from .. import exceptions


def create_barcode(
    self: "DBHandler", name: str, sequence: str, well: str | None, type: BarcodeTypeEnum, adapter_id: int
) -> models.Barcode:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (adapter := self.session.get(models.Adapter, adapter_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Adapter with id '{adapter_id}', not found.")
    
    barcode = models.Barcode(
        name=name.strip(),
        sequence=sequence.strip(),
        well=well,
        type_id=type.id,
        adapter_id=adapter_id,
        index_kit_id=adapter.index_kit_id
    )

    self.session.add(barcode)
    self.session.commit()
    self.session.refresh(barcode)

    if not persist_session:
        self.close_session()

    return barcode


def get_barcode(
    self: "DBHandler", barcode_id: int
) -> models.Barcode | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    barcode = self.session.get(models.Barcode, barcode_id)

    if not persist_session:
        self.close_session()

    return barcode


def get_barcodes(
    self: "DBHandler", index_kit_id: Optional[int] = None,
    adapter_id: Optional[int] = None,
    type: Optional[BarcodeTypeEnum] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[models.Barcode], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Barcode)

    if index_kit_id is not None:
        query = query.filter(models.Barcode.index_kit_id == index_kit_id)

    if type is not None:
        query = query.filter(models.Barcode.type_id == type.id)

    if adapter_id is not None:
        query = query.filter(models.Barcode.adapter_id == adapter_id)

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if sort_by is not None:
        column = getattr(models.Barcode, sort_by)
        query = query.order_by(sa.desc(column) if descending else column)

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    barcodes = query.all()

    if not persist_session:
        self.close_session()

    return barcodes, n_pages


def get_barcode_from_kit(
    self: "DBHandler", index_kit_id: int, name: str, type: BarcodeTypeEnum
) -> models.Barcode | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    barcode = self.session.query(models.Barcode).where(
        models.Barcode.index_kit_id == index_kit_id,
        models.Barcode.name == name,
        models.Barcode.type_id == type.id
    ).first()

    if not persist_session:
        self.close_session()

    return barcode


def query_barcode_sequences(self: "DBHandler", sequence: str, limit: Optional[int] = PAGE_LIMIT) -> list[models.Barcode]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Barcode)

    query = query.order_by(
        sa.func.similarity(models.Barcode.sequence, sequence).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    barcodes = query.all()

    if not persist_session:
        self.close_session()

    return barcodes