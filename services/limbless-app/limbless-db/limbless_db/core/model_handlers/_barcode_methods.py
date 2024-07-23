import math
from typing import Optional

import sqlalchemy as sa

from ... import models, PAGE_LIMIT
from ...categories import BarcodeTypeEnum
from .. import exceptions


def create_barcode(
    self, name: str, sequence: str, well: str | None, type: BarcodeTypeEnum, adapter_id: int
) -> models.Barcode:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (adapter := self._session.get(models.Adapter, adapter_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Adapter with id '{adapter_id}', not found.")
    
    barcode = models.Barcode(
        name=name.strip(),
        sequence=sequence.strip(),
        well=well,
        type_id=type.id,
        adapter_id=adapter_id,
        index_kit_id=adapter.index_kit_id
    )

    self._session.add(barcode)
    self._session.commit()
    self._session.refresh(barcode)

    if not persist_session:
        self.close_session()

    return barcode


def get_barcode(
    self, barcode_id: int
) -> Optional[models.Barcode]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    barcode = self._session.get(models.Barcode, barcode_id)

    if not persist_session:
        self.close_session()

    return barcode


def get_barcodes(
    self, index_kit_id: Optional[int] = None,
    adapter_id: Optional[int] = None,
    type: Optional[BarcodeTypeEnum] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[models.Barcode], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Barcode)

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



    
