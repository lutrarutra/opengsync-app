import math
from typing import Optional

import sqlalchemy as sa
from ...categories import KitTypeEnum, KitType
from ... import PAGE_LIMIT, models
from ..DBBlueprint import DBBlueprint


class KitBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self,
        name: str,
        identifier: str,
        kit_type: KitTypeEnum = KitType.LIBRARY_KIT,
        flush: bool = True
    ) -> models.Kit:

        kit = models.Kit(
            name=name,
            identifier=identifier,
            kit_type_id=kit_type.id,
        )
        self.db.session.add(kit)

        if flush:
            self.db.flush()
        return kit

    @DBBlueprint.transaction
    def get(self, id: int | None = None, identifier: Optional[str] = None, name: Optional[str] = None) -> models.Kit | None:
        if id is None and identifier is None and name is None:
            raise ValueError("Either id or identifier must be provided.")

        if id is not None:
            kit = self.db.session.get(models.Kit, id)
        elif identifier is not None:
            kit = self.db.session.query(models.Kit).where(models.Kit.identifier == identifier).first()
        else:
            kit = self.db.session.query(models.Kit).where(models.Kit.name == name).first()
        return kit

    @DBBlueprint.transaction
    def get_with_name(self, name: str) -> models.Kit | None:
        kit = self.db.session.query(models.Kit).where(models.Kit.name == name).first()
        return kit
    
    @DBBlueprint.transaction
    def get_with_identifier(self, identifier: str) -> models.Kit | None:
        kit = self.db.session.query(models.Kit).where(models.Kit.identifier == identifier).first()
        return kit

    @DBBlueprint.transaction
    def find(
        self,
        type: KitTypeEnum | None = None,
        type_in: list[KitTypeEnum] | None = None,
        protocol: models.Protocol | None = None,
        protocol_id: int | None = None,
        not_in_protocol: models.Protocol | None = None,
        name: str | None = None,
        identifier: str | None = None,
        id: int | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = 0,
        sort_by: Optional[str] = None, descending: bool = False,
        page: int | None = None
    ) -> tuple[list[models.Kit], int | None]:

        query = self.db.session.query(models.Kit)

        if type is not None:
            query = query.where(models.Kit.kit_type_id == type.id)

        if type_in is not None:
            query = query.where(models.Kit.kit_type_id.in_([t.id for t in type_in]))

        if protocol is not None:
            query = query.where(
                sa.exists().where(
                    (models.links.ProtocolKitLink.protocol_id == protocol.id) &
                    (models.links.ProtocolKitLink.kit_id == models.Kit.id)
                )
            )
        elif protocol_id is not None:
            query = query.where(
                sa.exists().where(
                    (models.links.ProtocolKitLink.protocol_id == protocol_id) &
                    (models.links.ProtocolKitLink.kit_id == models.Kit.id)
                )
            )

        if not_in_protocol is not None:
            query = query.where(
                ~sa.exists().where(
                    (models.links.ProtocolKitLink.protocol_id == not_in_protocol.id) &
                    (models.links.ProtocolKitLink.kit_id == models.Kit.id)
                )
            )

        if sort_by is not None:
            if sort_by not in models.Kit.sortable_fields:
                raise ValueError(f"Invalid sort_by field: {sort_by}")
            attr = getattr(models.Kit, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        if id is not None:
            query = query.where(models.Kit.id == id)
        if name is not None:
            query = query.order_by(sa.nulls_last(sa.func.similarity(models.Kit.name, name).desc()))
        elif identifier is not None:
            query = query.order_by(sa.nulls_last(sa.func.similarity(models.Kit.identifier, identifier).desc()))

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
        self, word: str, limit: int | None = PAGE_LIMIT, kit_type: Optional[KitTypeEnum] = None,
    ) -> list[models.Kit]:
        query = self.db.session.query(models.Kit)
        if kit_type is not None:
            query = query.where(models.Kit.kit_type_id == kit_type.id)

        query = query.order_by(
            sa.func.similarity(models.Kit.identifier + ' ' + models.Kit.name, word).desc()
        )

        if limit is not None:
            query = query.limit(limit)

        res = query.all()
        return res

    @DBBlueprint.transaction
    def update(self, kit: models.Kit):
        self.db.session.add(kit)

    @DBBlueprint.transaction
    def delete(self, kit: models.Kit, flush: bool = True):
        self.db.session.query(models.Feature).where(
            sa.and_(
                models.Feature.feature_kit_id == kit.id,
                ~sa.exists(models.links.LibraryFeatureLink.feature_id == models.Feature.id)
            )
        ).delete()
        self.db.session.delete(kit)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def __getitem__(self, id: int | str) -> models.Kit:
        if isinstance(id, str):
            if (kit := self.get(identifier=id)) is None:
                raise KeyError(f"Kit with identifier '{id}' does not exist")
        else:
            if (kit := self.db.session.get(models.Kit, id)) is None:
                raise KeyError(f"Kit with id {id} does not exist")
        return kit