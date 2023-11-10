import math
from typing import Optional

from sqlmodel import and_
import pandas as pd

from ... import models, logger, PAGE_LIMIT
from .. import exceptions

from ._adapter_methods import get_adapter_by_name, create_adapter


def create_barcode(
    self, sequence: str, adapter: str,
    type: str, index_kit_id: int,
    workflow: Optional[str],
    commit: bool = True
) -> models.Barcode:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (index_kit := self._session.get(models.IndexKit, index_kit_id)) is None:
        raise exceptions.ElementDoesNotExist(f"index_kit with id '{index_kit_id}', not found.")

    if (adapter := get_adapter_by_name(self, index_kit_id, adapter)) is None:
        adapter = create_adapter(self, adapter, index_kit_id, commit=True)

    if self._session.query(models.Barcode).where(
        and_(
            models.Barcode.sequence == sequence,
            models.Barcode.adapter_id == adapter.id,
            models.Barcode.type == type,
            models.Barcode.index_kit_id == index_kit.id,
            models.Barcode.workflow == workflow
        )
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"SeqIndex with sequence '{sequence} ({type} [{workflow}])', already exists in index-kit '{index_kit.name}'.")

    barcode = models.Barcode(
        sequence=sequence,
        adapter_id=adapter.id,
        type=type,
        workflow=workflow,
        index_kit_id=index_kit.id
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