import math
from typing import Optional

from ... import models, PAGE_LIMIT
from ...core.categories import BarcodeType


def create_barcode(
    self, sequence: str,
    barcode_type: BarcodeType,
    adapter: Optional[str] = None,
    index_kit_id: Optional[int] = None,
    commit: bool = True
) -> models.Barcode:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    barcode = models.Barcode(
        sequence=sequence,
        adapter=adapter,
        index_kit_id=index_kit_id,
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


def update_barcode(
    self, barcode: models.Barcode,
    commit: bool = True
) -> models.Barcode:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    self._session.add(barcode)
    if commit:
        self._session.commit()
        self._session.refresh(barcode)

    if not persist_session:
        self.close_session()
    return barcode


def reverse_complement(
    self, barcode_id: int,
) -> models.Barcode:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    barcode = self._session.get(models.Barcode, barcode_id)
    barcode.sequence = models.Barcode.reverse_complement(barcode.sequence)
    self._session.add(barcode)
    self._session.commit()
    self._session.refresh(barcode)

    if not persist_session:
        self.close_session()
    return barcode
