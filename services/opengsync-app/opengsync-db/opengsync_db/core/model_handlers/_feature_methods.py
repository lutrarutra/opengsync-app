import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from ...categories import FeatureTypeEnum, FeatureType
from .. import exceptions


def create_feature(
    self: "DBHandler",
    name: str,
    sequence: str,
    pattern: str,
    read: str,
    type: FeatureTypeEnum,
    feature_kit_id: Optional[int] = None,
    target_name: Optional[str] = None,
    target_id: Optional[str] = None,
    flush: bool = True
) -> models.Feature:
    if not (persist_session := self._session is not None):
        self.open_session()

    if feature_kit_id is not None:
        if (kit := self.session.get(models.FeatureKit, feature_kit_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Feature kit with id {feature_kit_id} does not exist")
        
        if self.session.query(models.Feature).where(
            models.Feature.sequence == sequence,
            models.Feature.pattern == pattern,
            models.Feature.read == read,
            models.Feature.feature_kit_id == feature_kit_id
        ).first():
            raise exceptions.NotUniqueValue("Duplicate feature definition in kit")
        if kit.kit_type == FeatureType.CMO:
            if self.session.query(models.Feature).where(
                models.Feature.name == name,
                models.Feature.feature_kit_id == feature_kit_id
            ).first():
                raise exceptions.NotUniqueValue("Duplicate names not allowed in CMO kits")

    feature = models.Feature(
        name=name.strip(),
        sequence=sequence.strip(),
        pattern=pattern.strip(),
        read=read.strip(),
        type_id=type.id,
        target_name=target_name.strip() if target_name else None,
        target_id=target_id.strip() if target_id else None,
        feature_kit_id=feature_kit_id
    )
    self.session.add(feature)

    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()
    return feature


def get_feature(self: "DBHandler", feature_id: int) -> models.Feature | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.Feature, feature_id)

    if not persist_session:
        self.close_session()
    return res


def get_features(
    self: "DBHandler", feature_kit_id: Optional[int] = None,
    library_id: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    count_pages: bool = False
) -> tuple[list[models.Feature], int | None]:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Feature)

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

    if not persist_session:
        self.close_session()

    return features, n_pages


def delete_feature(self: "DBHandler", feature_id: int, flush: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (feature := self.session.get(models.Feature, feature_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Feature with id {feature_id} does not exist")
    
    self.session.delete(feature)

    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()


def update_feature(
    self: "DBHandler", feature: models.Feature
) -> models.Feature:
    if not (persist_session := self._session is not None):
        self.open_session()

    self.session.add(feature)

    if not persist_session:
        self.close_session()

    return feature

    
def get_features_from_kit_by_feature_name(
    self: "DBHandler", feature_name: str, feature_kit_id: int
) -> list[models.Feature]:
    if not (persist_session := self._session is not None):
        self.open_session()

    feature = self.session.query(models.Feature).where(
        models.Feature.name == feature_name,
        models.Feature.feature_kit_id == feature_kit_id
    ).all()

    if not persist_session:
        self.close_session()

    return feature


def delete_orphan_features(
    self: "DBHandler", flush: bool = True
) -> None:
    if not (persist_session := self._session is not None):
        self.open_session()

    features = self.session.query(models.Feature).where(
        models.Feature.feature_kit_id.is_(None),
        ~sa.exists().where(models.links.LibraryFeatureLink.feature_id == models.Feature.id)
    ).all()

    for feature in features:
        self.session.delete(feature)

    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()