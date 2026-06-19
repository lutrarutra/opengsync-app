import sqlalchemy as sa


from ..models import FeatureKit, Protocol, links
from ..categories import KitType, FeatureType
from ..core import utils


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


def search(
    name: str | None = None,
    identifier: str | None = None,
    name_weight: float = 0.5,
    identifier_weight: float = 0.5,
    statement: sa.Select[tuple[FeatureKit]] = sa.select(FeatureKit),
) -> sa.Select[tuple[FeatureKit]]:
    filter_conditions: list[sa.ColumnElement[bool]] = []
    relevance = sa.literal(0.0)

    if name is not None:
        filter_conditions.append(utils.safe_trgm_search(FeatureKit.name, name))
        relevance += sa.func.similarity(FeatureKit.name, name) * name_weight

    if identifier is not None:
        filter_conditions.append(utils.safe_ilike(FeatureKit.identifier, identifier))
        relevance += sa.func.similarity(FeatureKit.identifier, identifier) * identifier_weight

    if not filter_conditions:
        return statement

    return (
        statement
        .where(sa.or_(*filter_conditions))
        .order_by(sa.nulls_last(relevance.desc()))
    )


def select(
    id: int | None = None,
    name: str | None = None,
    identifier: str | None = None,
    type: FeatureType | None = None,
    type_in: list[FeatureType] | None = None,
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
    return statement
