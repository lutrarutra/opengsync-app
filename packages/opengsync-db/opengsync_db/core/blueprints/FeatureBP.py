import math
from typing import Optional

import sqlalchemy as sa

from ..DBBlueprint import DBBlueprint
from ... import models, PAGE_LIMIT
from ...categories import FeatureType
from .. import exceptions


class FeatureBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self,
        identifier: str | None,
        name: str,
        sequence: str,
        pattern: str,
        read: str,
        type: FeatureType,
        feature_kit_id: int | None = None,
        target_name: str | None = None,
        target_id: str | None = None,
        flush: bool = True
    ) -> models.Feature:
        feature = models.Feature(
            identifier=identifier.strip() if identifier else None,
            name=name.strip(),
            sequence=sequence.strip(),
            pattern=pattern.strip(),
            read=read.strip(),
            type_id=type.id,
            target_name=target_name.strip() if target_name else None,
            target_id=target_id.strip() if target_id else None,
            feature_kit_id=feature_kit_id
        )
        self.db.session.add(feature)

        if flush:
            self.db.flush()
        return feature

    @DBBlueprint.transaction
    def get(self, feature_id: int) -> models.Feature | None:
        res = self.db.session.get(models.Feature, feature_id)
        return res

    @DBBlueprint.transaction
    def find(
        self, feature_kit_id: int | None = None,
        library_id: int | None = None,
        sort_by: str | None = None, descending: bool = False,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        count_pages: bool = False
    ) -> tuple[list[models.Feature], int | None]:
        query = self.db.session.query(models.Feature)

        if feature_kit_id is not None:
            query = query.where(
                models.Feature.feature_kit_id == feature_kit_id
            )

        if library_id is not None:
            query = query.join(
                models.links.LibraryFeatureLink,
                models.links.LibraryFeatureLink.feature_id == models.Feature.id
            ).where(
                models.links.LibraryFeatureLink.library_id == library_id
            )

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

        if sort_by is not None:
            attr = getattr(models.Feature, sort_by)
            if descending:
                attr = attr.desc()

            query = query.order_by(attr)

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        features = query.all()
        return features, n_pages

    @DBBlueprint.transaction
    def delete(self, feature_id: int, flush: bool = True):
        if (feature := self.db.session.get(models.Feature, feature_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Feature with id {feature_id} does not exist")
        
        self.db.session.delete(feature)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def update(self, feature: models.Feature):
        self.db.session.add(feature)

    @DBBlueprint.transaction
    def get_from_kit_by_name(
        self, feature_name: str, feature_kit_id: int
    ) -> list[models.Feature]:
        feature = self.db.session.query(models.Feature).where(
            models.Feature.name == feature_name,
            models.Feature.feature_kit_id == feature_kit_id
        ).all()
        return feature

    @DBBlueprint.transaction
    def delete_orphan(
        self, flush: bool = True
    ) -> None:
        features = self.db.session.query(models.Feature).where(
            models.Feature.feature_kit_id.is_(None),
            ~sa.exists().where(models.links.LibraryFeatureLink.feature_id == models.Feature.id)
        ).all()

        for feature in features:
            self.db.session.delete(feature)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def __getitem__(self, id: int) -> models.Feature:
        if (feature := self.db.session.get(models.Feature, id)) is None:
            raise exceptions.ElementDoesNotExist(f"Feature with id {id} does not exist")
        return feature