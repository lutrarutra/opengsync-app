import math
from typing import Optional

import sqlalchemy as sa
from ...categories import ServiceType, ServiceTypeEnum
from ... import PAGE_LIMIT, models
from ..DBBlueprint import DBBlueprint


class ProtocolBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self,
        name: str,
        service_type: ServiceTypeEnum,
        read_structure: str | None = None,
        flush: bool = True
    ) -> models.Protocol:

        protocol = models.Protocol(
            name=name,
            service_type_id=service_type.id,
            read_structure=read_structure
        )
        self.db.session.add(protocol)

        if flush:
            self.db.flush()
        return protocol

    @DBBlueprint.transaction
    def get(self, id: int) -> models.Protocol | None:
        return self.db.session.get(models.Protocol, id)
    
    @DBBlueprint.transaction
    def get_by_name(self, name: str) -> models.Protocol | None:
        return self.db.session.query(models.Protocol).where(models.Protocol.name == name).first()

    @DBBlueprint.transaction
    def find(
        self,
        id: int | None = None,
        name: str | None = None,
        service_type: ServiceTypeEnum | None = None,
        service_type_in: list[ServiceTypeEnum] | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = 0,
        sort_by: Optional[str] = None, descending: bool = False,
        page: int | None = None,
    ) -> tuple[list[models.Protocol], int | None]:

        query = self.db.session.query(models.Protocol)

        if service_type is not None:
            query = query.where(models.Protocol.service_type_id == service_type.id)

        if service_type_in is not None:
            query = query.where(models.Protocol.service_type_id.in_([t.id for t in service_type_in]))

        if sort_by is not None:
            if sort_by not in models.Protocol.sortable_fields:
                raise ValueError(f"Invalid sort_by field: {sort_by}")
            attr = getattr(models.Protocol, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        if id is not None:
            query = query.where(models.Protocol.id == id)
        if name is not None:
            query = query.order_by(sa.nulls_last(sa.func.similarity(models.Protocol.name, name).desc()))

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

    @DBBlueprint.transaction
    def query(
        self, word: str, limit: int | None = PAGE_LIMIT, service_type: Optional[ServiceTypeEnum] = None,
    ) -> list[models.Protocol]:
        query = self.db.session.query(models.Protocol)

        if service_type is not None:
            query = query.where(models.Protocol.service_type_id == service_type.id)

        query = query.order_by(sa.func.similarity(models.Protocol.name, word).desc())

        if limit is not None:
            query = query.limit(limit)

        res = query.all()
        return res

    @DBBlueprint.transaction
    def update(self, protocol: models.Protocol):
        self.db.session.add(protocol)

    @DBBlueprint.transaction
    def delete(self, protocol: models.Protocol, flush: bool = True):
        self.db.session.delete(protocol)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def __getitem__(self, id: int) -> models.Protocol:
        if (protocol := self.get(id)) is None:
            raise KeyError(f"Protocol with id '{id}' does not exist")

        return protocol