import math
from typing import Optional

import sqlalchemy as sa

from ...categories import IndexTypeEnum, LabChecklistTypeEnum, KitType
from ... import models, PAGE_LIMIT
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class IndexKitBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self, identifier: str, name: str,
        supported_protocols: list[LabChecklistTypeEnum],
        type: IndexTypeEnum,
        flush: bool = True
    ) -> models.IndexKit:
        if self.db.session.query(models.IndexKit).where(models.IndexKit.name == name).first():
            raise exceptions.NotUniqueValue(f"index_kit with name '{name}', already exists.")

        seq_kit = models.IndexKit(
            identifier=identifier.strip(),
            name=name.strip(),
            type_id=type.id,
            kit_type_id=KitType.INDEX_KIT.id,
            supported_protocol_ids=[p.id for p in supported_protocols]
        )
        self.db.session.add(seq_kit)

        if flush:
            self.db.flush()

        return seq_kit

    @DBBlueprint.transaction
    def get(self, id: int) -> models.IndexKit | None:
        res = self.db.session.get(models.IndexKit, id)
        return res

    @DBBlueprint.transaction
    def get_with_name(self, name: str) -> models.IndexKit | None:
        res = self.db.session.query(models.IndexKit).where(models.IndexKit.name == name).first()
        return res

    @DBBlueprint.transaction
    def get_with_identifier(
        self, identifier: str
    ) -> models.IndexKit | None:
        res = self.db.session.query(models.IndexKit).where(models.IndexKit.identifier == identifier).first()
        return res

    @DBBlueprint.transaction
    def query(
        self, word: str, limit: int | None = PAGE_LIMIT, index_type: Optional[IndexTypeEnum] = None,
        index_type_in: Optional[list[IndexTypeEnum]] = None
    ) -> list[models.IndexKit]:
        query = self.db.session.query(models.IndexKit)
        query = query.where(models.IndexKit.kit_type_id == KitType.INDEX_KIT.id)

        if index_type is not None:
            query = query.where(models.IndexKit.type_id == index_type.id)

        if index_type_in is not None:
            query = query.where(models.IndexKit.type_id.in_([t.id for t in index_type_in]))

        query = query.order_by(
            sa.func.similarity(models.IndexKit.identifier + ' ' + models.IndexKit.name, word).desc()
        )

        if limit is not None:
            query = query.limit(limit)

        res = query.all()
        return res

    @DBBlueprint.transaction
    def remove_all_barcodes(
        self, index_kit_id: int, flush: bool = True
    ) -> models.IndexKit:
        if (index_kit := self.db.session.get(models.IndexKit, index_kit_id)) is None:
            raise exceptions.ElementDoesNotExist(f"IndexKit with id '{index_kit_id}' not found.")
        
        for adapter in index_kit.adapters:
            for barcode in adapter.barcodes_i7:
                self.db.session.delete(barcode)
                
            for barcode in adapter.barcodes_i5:
                self.db.session.delete(barcode)

            self.db.session.delete(adapter)

        if flush:
            self.db.flush()
        return index_kit

    @DBBlueprint.transaction
    def find(
        self, type_in: list[IndexTypeEnum] | None = None,
        name: str | None = None,
        identifier: str | None = None,
        identifier_name: str | None = None,
        id: int | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: str | None = None, descending: bool = False,
        page: int | None = None,
    ) -> tuple[list[models.IndexKit], int | None]:
        query = self.db.session.query(models.IndexKit)

        if type_in is not None:
            query = query.where(models.IndexKit.type_id.in_([t.id for t in type_in]))

        if sort_by is not None:
            attr = getattr(models.IndexKit, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        if id is not None:
            query = query.where(models.IndexKit.id == id)
        if name is not None:
            query = query.order_by(sa.nulls_last(sa.func.similarity(models.IndexKit.name, name).desc()))
        elif identifier is not None:
            query = query.order_by(sa.nulls_last(sa.func.similarity(models.IndexKit.identifier, identifier).desc()))
        if identifier_name is not None:
            query = query.order_by(sa.nulls_last(sa.func.similarity(
                models.IndexKit.identifier + ' ' + models.IndexKit.name, identifier_name
            ).desc()))

        if page is not None:
            if limit is None:
                raise ValueError("Limit must be provided when page is provided")
            
            count = query.count()
            n_pages = math.ceil(count / limit)
            query = query.offset(min(page, max(0, n_pages - 1)) * limit)
        else:
            n_pages = None

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        res = query.all()
        return res, n_pages

    @DBBlueprint.transaction
    def update(self, index_kit: models.IndexKit):
        self.db.session.add(index_kit)

    @DBBlueprint.transaction
    def __getitem__(self, id: int | str) -> models.IndexKit:
        if isinstance(id, str):
            if (index_kit := self.get_with_identifier(id)) is None:
                raise exceptions.ElementDoesNotExist(f"IndexKit with identifier '{id}' not found.")
        else:
            if (index_kit := self.get(id)) is None:
                raise exceptions.ElementDoesNotExist(f"IndexKit with id '{id}' not found.")
        return index_kit