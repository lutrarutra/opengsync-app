import math
from typing import Optional

from sqlmodel import and_
import pandas as pd

from ... import models, logger, PAGE_LIMIT
from .. import exceptions

from ._adapter_methods import get_adapter
from ...categories import BarcodeType


def create_barcode(
    self, sequence: str,
    adapter_id: int,
    barcode_type: BarcodeType,
    commit: bool = True
) -> models.Barcode:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (adapter := get_adapter(self, adapter_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Adapter with id '{adapter_id}', not found.")

    if self._session.query(models.Barcode).where(
        and_(
            models.Barcode.sequence == sequence,
            models.Barcode.adapter_id == adapter_id,
            models.Barcode.type_id == barcode_type.value.id
        )
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"SeqIndex with sequence '{sequence} ({barcode_type})', already exists for adapter '{adapter.name}'.")

    barcode = models.Barcode(
        sequence=sequence,
        adapter_id=adapter_id,
        type_id=barcode_type.value.id
    )

    self._session.add(barcode)
    if commit:
        self._session.commit()
        self._session.refresh(barcode)

    if not persist_session:
        self.close_session()
    return barcode


def get_barcode(self, id: int) -> models.Barcode:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Barcode).where(models.Barcode.id == id).first()
    if not persist_session:
        self.close_session()
    return res


def get_seqbarcodes(
    self, limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False
) -> tuple[list[models.Barcode], int]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Barcode)

    if sort_by is not None:
        attr = getattr(models.Barcode, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    n_pages = math.ceil(query.count() / limit) if limit is not None else 1

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    barcodes = query.all()

    if not persist_session:
        self.close_session()

    return barcodes, n_pages


def get_num_seqbarcodes(self) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Barcode).count()
    if not persist_session:
        self.close_session()
    return res