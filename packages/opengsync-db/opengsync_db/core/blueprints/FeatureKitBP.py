import math
from typing import Optional

import sqlalchemy as sa

from ... import models, PAGE_LIMIT
from .. import exceptions
from ...categories import FeatureTypeEnum, KitType

from ..DBBlueprint import DBBlueprint


class FeatureKitBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self, identifier: str, name: str,
        type: FeatureTypeEnum, flush: bool = True
    ) -> models.FeatureKit:
        if self.db.session.query(models.FeatureKit).where(models.FeatureKit.name == name).first():
            raise exceptions.NotUniqueValue(f"Feature kit with name '{name}', already exists.")

        feature_kit = models.FeatureKit(
            name=name.strip(),
            identifier=identifier.strip(),
            type_id=type.id,
            kit_type_id=KitType.FEATURE_KIT.id,
        )
        self.db.session.add(feature_kit)

        if flush:
            self.db.flush()
        return feature_kit

    @DBBlueprint.transaction
    def get(self, id: int) -> models.FeatureKit | None:
        res = self.db.session.get(models.FeatureKit, id)
        return res

    @DBBlueprint.transaction
    def get_with_name(self, name: str) -> models.FeatureKit | None:
        res = self.db.session.query(models.FeatureKit).where(models.FeatureKit.name == name).first()
        return res
    
    @DBBlueprint.transaction
    def get_with_identifier(self, identifier: str) -> models.FeatureKit | None:
        res = self.db.session.query(models.FeatureKit).where(models.FeatureKit.identifier == identifier).first()
        return res

    @DBBlueprint.transaction
    def find(
        self,
        type: FeatureTypeEnum | None = None,
        type_in: list[FeatureTypeEnum] | None = None,
        name: str | None = None,
        identifier: str | None = None,
        id: int | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: str | None = None, descending: bool = False,
        page: int | None = None,
    ) -> tuple[list[models.FeatureKit], int | None]:
        
        query = self.db.session.query(models.FeatureKit)
        if type is not None:
            query = query.filter(models.FeatureKit.type_id == type.id)

        if type_in is not None:
            query = query.filter(models.FeatureKit.type_id.in_([t.id for t in type_in]))

        if sort_by is not None:
            sort_attr = getattr(models.FeatureKit, sort_by)
            if descending:
                sort_attr = sort_attr.desc()
            query = query.order_by(sort_attr)

        if id is not None:
            query = query.where(models.FeatureKit.id == id)
        if name is not None:
            query = query.order_by(sa.nulls_last(sa.func.similarity(models.FeatureKit.name, name).desc()))
        elif identifier is not None:
            query = query.order_by(sa.nulls_last(sa.func.similarity(models.FeatureKit.identifier, identifier).desc()))

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

        feature_kits = query.all()
        return feature_kits, n_pages

    @DBBlueprint.transaction
    def update(self, feature_kit: models.FeatureKit):
        self.db.session.add(feature_kit)

    @DBBlueprint.transaction
    def delete(self, kit: models.FeatureKit, flush: bool = True):
        self.db.session.delete(kit)
        self.db.features.delete_orphan()

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def remove_all_features(self, feature_kit_id: int) -> models.FeatureKit:
        if (feature_kit := self.db.session.get(models.FeatureKit, feature_kit_id)) is None:
            raise exceptions.ElementDoesNotExist(f"FeatureKit with id '{feature_kit_id}' not found.")
        
        for feature in feature_kit.features:
            self.db.session.delete(feature)
        return feature_kit
    
    @DBBlueprint.transaction
    def __getitem__(self, id: int | str) -> models.FeatureKit:
        if isinstance(id, int):
            if (kit := self.db.session.get(models.FeatureKit, id)) is None:
                raise exceptions.ElementDoesNotExist(f"FeatureKit with id '{id}' not found.")
        else:
            if (kit := self.get_with_identifier(id)) is None:
                raise exceptions.ElementDoesNotExist(f"FeatureKit with identifier '{id}' not found.")
        return kit