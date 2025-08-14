import math
from typing import Optional

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
    def find(
        self,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        count_pages: bool = False
    ) -> tuple[list[models.FeatureKit], int | None]:
        query = self.db.session.query(models.FeatureKit)

        if sort_by is not None:
            sort_attr = getattr(models.FeatureKit, sort_by)
            if descending:
                sort_attr = sort_attr.desc()
            query = query.order_by(sort_attr)

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        feature_kits = query.all()
        return feature_kits, n_pages

    @DBBlueprint.transaction
    def update(self, feature_kit: models.FeatureKit) -> models.FeatureKit:
        self.db.session.add(feature_kit)
        return feature_kit

    @DBBlueprint.transaction
    def delete(self, feature_kit_id: int, flush: bool = True):
        if (feature_kit := self.db.session.get(models.FeatureKit, feature_kit_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Feature kit with id '{feature_kit_id}', not found.")
        
        self.db.session.delete(feature_kit)
        self.delete_orphan_features()

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def remove_all_features(self, feature_kit_id: int) -> models.FeatureKit:
        if (feature_kit := self.db.session.get(models.FeatureKit, feature_kit_id)) is None:
            raise exceptions.ElementDoesNotExist(f"FeatureKit with id '{feature_kit_id}' not found.")
        
        for feature in feature_kit.features:
            self.db.session.delete(feature)
        return feature_kit