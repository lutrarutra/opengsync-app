import math
from typing import Optional

import sqlalchemy as sa

from ... import models, PAGE_LIMIT
from ...categories import BarcodeTypeEnum
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class BarcodeBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self, name: str, sequence: str, well: str | None,
        type: BarcodeTypeEnum, adapter_id: int, flush: bool = True
    ) -> models.Barcode:
        if (adapter := self.db.session.get(models.Adapter, adapter_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Adapter with id '{adapter_id}', not found.")
        
        barcode = models.Barcode(
            name=name.strip(),
            sequence=sequence.strip(),
            well=well,
            type_id=type.id,
            adapter_id=adapter_id,
            index_kit_id=adapter.index_kit_id
        )
        self.db.session.add(barcode)

        if flush:
            self.db.flush()
        return barcode

    @DBBlueprint.transaction
    def get(
        self, barcode_id: int
    ) -> models.Barcode | None:
        barcode = self.db.session.get(models.Barcode, barcode_id)
        return barcode

    @DBBlueprint.transaction
    def find(
        self, index_kit_id: int | None = None,
        adapter_id: int | None = None,
        type: Optional[BarcodeTypeEnum] = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        count_pages: bool = False
    ) -> tuple[list[models.Barcode], int | None]:
        query = self.db.session.query(models.Barcode)

        if index_kit_id is not None:
            query = query.filter(models.Barcode.index_kit_id == index_kit_id)

        if type is not None:
            query = query.filter(models.Barcode.type_id == type.id)

        if adapter_id is not None:
            query = query.filter(models.Barcode.adapter_id == adapter_id)

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

        if sort_by is not None:
            column = getattr(models.Barcode, sort_by)
            query = query.order_by(sa.desc(column) if descending else column)

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        barcodes = query.all()
        return barcodes, n_pages

    @DBBlueprint.transaction
    def get_from_kit(
        self, index_kit_id: int, name: str, type: BarcodeTypeEnum
    ) -> models.Barcode | None:
        barcode = self.db.session.query(models.Barcode).where(
            models.Barcode.index_kit_id == index_kit_id,
            models.Barcode.name == name,
            models.Barcode.type_id == type.id
        ).first()
        return barcode

    @DBBlueprint.transaction
    def query_sequence(self, sequence: str, limit: int | None = PAGE_LIMIT) -> list[models.Barcode]:
        query = self.db.session.query(models.Barcode)

        query = query.order_by(
            sa.func.similarity(models.Barcode.sequence, sequence).desc()
        )

        if limit is not None:
            query = query.limit(limit)

        barcodes = query.all()
        return barcodes
    
    @DBBlueprint.transaction
    def __getitem__(self, id: int) -> models.Barcode:
        if (barcode := self.get(id)) is None:
            raise exceptions.ElementDoesNotExist(f"Barcode with id '{id}' does not exist.")
        return barcode