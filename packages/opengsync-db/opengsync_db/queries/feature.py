import sqlalchemy as sa

from ..models import Feature, links
from ..categories import FeatureType


def create(
    identifier: str | None,
    name: str,
    sequence: str,
    pattern: str,
    read: str,
    type: FeatureType,
    feature_kit_id: int | None = None,
    target_name: str | None = None,
    target_id: str | None = None,
) -> Feature:
    return Feature(
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


def select(
    id: int | None = None,
    feature_kit_id: int | None = None,
    library_id: int | None = None,
    type: FeatureType | None = None,
    type_in: list[FeatureType] | None = None,
    search_name: str | None = None,
    search_identifier: str | None = None,
    statement: sa.Select[tuple[Feature]] = sa.select(Feature),
) -> sa.Select[tuple[Feature]]:
    if id is not None:
        statement = statement.where(Feature.id == id)
    if feature_kit_id is not None:
        statement = statement.where(
            Feature.feature_kit_id == feature_kit_id
        )
    if library_id is not None:
        statement = statement.join(
            links.LibraryFeatureLink,
            links.LibraryFeatureLink.feature_id == Feature.id
        ).where(
            links.LibraryFeatureLink.library_id == library_id
        )
    if type is not None:
        statement = statement.where(Feature.type_id == type.id)
    if type_in is not None:
        statement = statement.where(Feature.type_id.in_([t.id for t in type_in]))
    
    if search_name is not None:
        statement = statement.order_by(sa.nulls_last(sa.func.similarity(Feature.name, search_name).desc()))
    elif search_identifier is not None:
        statement = statement.order_by(sa.nulls_last(sa.func.similarity(Feature.identifier, search_identifier).desc()))
    return statement