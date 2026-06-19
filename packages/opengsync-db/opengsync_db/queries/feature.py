import sqlalchemy as sa

from ..models import Feature, links
from ..categories import FeatureType
from ..core import utils


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


def search(
    name: str | None = None,
    identifier: str | None = None,
    name_weight: float = 0.5,
    identifier_weight: float = 0.5,
    statement: sa.Select[tuple[Feature]] = sa.select(Feature),
) -> sa.Select[tuple[Feature]]:
    filter_conditions: list[sa.ColumnElement[bool]] = []
    relevance = sa.literal(0.0)

    if name is not None:
        filter_conditions.append(utils.safe_trgm_search(Feature.name, name))
        relevance += sa.func.similarity(Feature.name, name) * name_weight

    if identifier is not None:
        filter_conditions.append(utils.safe_ilike(Feature.identifier, identifier))
        relevance += sa.func.similarity(Feature.identifier, identifier) * identifier_weight

    if not filter_conditions:
        return statement

    return (
        statement
        .where(sa.or_(*filter_conditions))
        .order_by(sa.nulls_last(relevance.desc()))
    )


def select(
    id: int | None = None,
    feature_kit_id: int | None = None,
    library_id: int | None = None,
    type: FeatureType | None = None,
    type_in: list[FeatureType] | None = None,
    statement: sa.Select[tuple[Feature]] = sa.select(Feature),
) -> sa.Select[tuple[Feature]]:
    return statement.where(*where_clauses(
        id=id, feature_kit_id=feature_kit_id, library_id=library_id, type=type, type_in=type_in,
    ))


def where_clauses(
    id: int | None = None,
    feature_kit_id: int | None = None,
    library_id: int | None = None,
    type: FeatureType | None = None,
    type_in: list[FeatureType] | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering features.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(Feature.id == id)
    if feature_kit_id is not None:
        clauses.append(Feature.feature_kit_id == feature_kit_id)
    if library_id is not None:
        clauses.append(
            sa.select(1).where(
                links.LibraryFeatureLink.feature_id == Feature.id,
                links.LibraryFeatureLink.library_id == library_id
            ).correlate_except(links.LibraryFeatureLink).exists()
        )
    if type is not None:
        clauses.append(Feature.type_id == type.id)
    if type_in is not None:
        clauses.append(Feature.type_id.in_([t.id for t in type_in]))

    return clauses