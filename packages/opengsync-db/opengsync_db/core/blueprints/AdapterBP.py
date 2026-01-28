import math
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.sql.operators import and_

from ... import models, PAGE_LIMIT
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class AdapterBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self, index_kit_id: int,
        well: str | None = None, flush: bool = True
    ) -> models.Adapter:
        if well is not None:
            if self.db.session.query(models.Adapter).where(
                and_(
                    models.Adapter.well == well,
                    models.Adapter.index_kit_id == index_kit_id
                )
            ).first():
                raise exceptions.NotUniqueValue(f"Adapter with plate_well '{well}', already exists.")

        adapter = models.Adapter(well=well, index_kit_id=index_kit_id,)
        self.db.session.add(adapter)

        if flush:
            self.db.flush()

        return adapter

    @DBBlueprint.transaction
    def get(self, id: int) -> models.Adapter | None:
        res = self.db.session.get(models.Adapter, id)
        return res

    @DBBlueprint.transaction
    def find(
        self, index_kit_id: int | None = None,
        name: str | None = None,
        id: int | None = None,
        well: str | None = None,
        sort_by: str | None = None, descending: bool = False,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        page: int | None = None,
    ) -> tuple[list[models.Adapter], int | None]:
        query = self.db.session.query(models.Adapter)

        if index_kit_id is not None:
            query = query.where(models.Adapter.index_kit_id == index_kit_id)

        if sort_by is not None:
            attr = getattr(models.Adapter, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        if id is not None:
            query = query.where(models.FeatureKit.id == id)
        if name is not None:
            query = query.join(
                models.Barcode,
                models.Barcode.adapter_id == models.Adapter.id
            ).order_by(sa.nulls_last(sa.func.similarity(models.Barcode.name, name).desc())).distinct(models.Adapter.id)
        if well is not None:
            query = query.where(models.Adapter.well == well)

        if page is not None:
            if limit is None:
                raise ValueError("Limit must be provided when page is provided")
            
            count = query.count()
            n_pages = math.ceil(count / limit)
            query = query.offset(min(page, max(0, n_pages - 1)) * limit)
        else:
            n_pages = None

        if limit is not None:
            query = query.limit(limit)

        if offset is not None:
            query = query.offset(offset)

        res = query.all()

        return res, n_pages