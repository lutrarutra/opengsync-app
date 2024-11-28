import math
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..DBHandler import DBHandler

from ... import models, PAGE_LIMIT
from .. import exceptions
from ...categories import FeatureTypeEnum, KitType


def create_feature_kit(
    self: "DBHandler", identifier: str, name: str,
    type: FeatureTypeEnum,
) -> models.FeatureKit:
    if not (persist_session := self._session is not None):
        self.open_session()

    if self.session.query(models.FeatureKit).where(models.FeatureKit.name == name).first():
        raise exceptions.NotUniqueValue(f"Feature kit with name '{name}', already exists.")

    feature_kit = models.FeatureKit(
        name=name.strip(),
        identifier=identifier.strip(),
        type_id=type.id,
        kit_type_id=KitType.FEATURE_KIT.id,
    )
    self.session.add(feature_kit)
    self.session.commit()
    self.session.refresh(feature_kit)

    if not persist_session:
        self.close_session()
    return feature_kit


def get_feature_kit(self: "DBHandler", id: int) -> models.FeatureKit | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.FeatureKit, id)

    if not persist_session:
        self.close_session()

    return res


def get_feature_kit_by_name(self: "DBHandler", name: str) -> models.FeatureKit | None:
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


def update_feature_kit(self: "DBHandler", feature_kit: models.FeatureKit) -> models.FeatureKit:
    if not (persist_session := self._session is not None):
        self.open_session()

    self.session.add(feature_kit)
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
    self.session.commit()

    if not persist_session:
        self.close_session()


def remove_all_features_from_kit(self: "DBHandler", feature_kit_id: int) -> models.FeatureKit:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (feature_kit := self.session.get(models.FeatureKit, feature_kit_id)) is None:
        raise exceptions.ElementDoesNotExist(f"FeatureKit with id '{feature_kit_id}' not found.")
    
    for feature in feature_kit.features:
        self.session.delete(feature)

    self.session.commit()
    self.session.refresh(feature_kit)

    if not persist_session:
        self.close_session()
    return feature_kit