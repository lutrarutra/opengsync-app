import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from .. import exceptions
from ...categories import FeatureTypeEnum


def create_feature_kit(
    self: "DBHandler", name: str,
    type: FeatureTypeEnum,
) -> models.FeatureKit:
    if not (persist_session := self._session is not None):
        self.open_session()

    if self.session.query(models.FeatureKit).where(models.FeatureKit.name == name).first():
        raise exceptions.NotUniqueValue(f"Feature kit with name '{name}', already exists.")

    feature_kit = models.FeatureKit(
        name=name.strip(),
        type_id=type.id,
    )
    self.session.add(feature_kit)
    self.session.commit()
    self.session.refresh(feature_kit)

    if not persist_session:
        self.close_session()
    return feature_kit


def get_feature_kit(self: "DBHandler", id: int) -> Optional[models.FeatureKit]:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.FeatureKit, id)

    if not persist_session:
        self.close_session()

    return res


def get_feature_kit_by_name(self: "DBHandler", name: str) -> Optional[models.FeatureKit]:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.query(models.FeatureKit).where(models.FeatureKit.name == name).first()
    if not persist_session:
        self.close_session()

    return res


def get_feature_kits(
    self: "DBHandler",
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[models.FeatureKit], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.FeatureKit)

    if sort_by is not None:
        sort_attr = getattr(models.FeatureKit, sort_by)
        if descending:
            sort_attr = sort_attr.desc()
        query = query.order_by(sort_attr)

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    feature_kits = query.all()

    if not persist_session:
        self.close_session()

    return feature_kits, n_pages


def update_feature_kit(
    self: "DBHandler", feature_kit: models.FeatureKit,
    commit: bool = True,
) -> models.FeatureKit:
    if not (persist_session := self._session is not None):
        self.open_session()

    self.session.add(feature_kit)
    if commit:
        self.session.commit()
        self.session.refresh(feature_kit)

    if not persist_session:
        self.close_session()

    return feature_kit


def delete_feature_kit(self: "DBHandler", feature_kit_id: int):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (feature_kit := self.session.get(models.FeatureKit, feature_kit_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Feature kit with id '{feature_kit_id}', not found.")
    
    for feature in feature_kit.features:
        self.session.delete(feature)

    self.session.delete(feature_kit)

    if not persist_session:
        self.close_session()


def query_feature_kits(
    self: "DBHandler", word: str, limit: Optional[int] = PAGE_LIMIT
) -> list[models.FeatureKit]:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.FeatureKit)

    query = query.order_by(
        sa.func.similarity(models.FeatureKit.name, word).desc(),
    )

    if limit is not None:
        query = query.limit(limit)

    feature_kits = query.all()

    if not persist_session:
        self.close_session()

    return feature_kits