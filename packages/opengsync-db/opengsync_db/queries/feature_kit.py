import sqlalchemy as sa


from ..models import FeatureKit, Protocol, links
from ..categories import KitType, FeatureType


def create(
    identifier: str,
    name: str,
    type: FeatureType
) -> FeatureKit:
    return FeatureKit(
        name=name.strip(),
        identifier=identifier.strip(),
        type_id=type.id,
        kit_type_id=KitType.FEATURE_KIT.id,
    )


def select(
    id: int | None = None,
    name: str | None = None,
    identifier: str | None = None,
    type: FeatureType | None = None,
    type_in: list[FeatureType] | None = None,
    search_name: str | None = None,
    search_identifier: str | None = None,
    search_identifier_name: str | None = None,
    statement: sa.Select[tuple[FeatureKit]] = sa.select(FeatureKit),
) -> sa.Select[tuple[FeatureKit]]:
    if id is not None:
        statement = statement.where(FeatureKit.id == id)
    if name is not None:
        statement = statement.where(FeatureKit.name == name)
    if identifier is not None:
        statement = statement.where(FeatureKit.identifier == identifier)
    if type is not None:
        statement = statement.where(FeatureKit.type_id == type.id)
    if type_in is not None:
        statement = statement.where(FeatureKit.type_id.in_([t.id for t in type_in]))

    if search_name is not None:
        statement = statement.order_by(sa.nulls_last(sa.func.similarity(FeatureKit.name, search_name).desc()))
    elif search_identifier is not None:
        statement = statement.order_by(sa.nulls_last(sa.func.similarity(FeatureKit.identifier, search_identifier).desc()))
    elif search_identifier_name is not None:
        statement = statement.order_by(sa.nulls_last(sa.func.similarity(
            FeatureKit.identifier + ' ' + FeatureKit.name, search_identifier_name
        ).desc()))
    return statement
