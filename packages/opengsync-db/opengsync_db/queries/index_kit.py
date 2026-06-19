import sqlalchemy as sa
from sqlalchemy import sql

from ..models import IndexKit
from ..categories import IndexType, KitType
from ..core import utils



def create(
    identifier: str,
    name: str,
    supported_protocol_ids: list[int],
    type: IndexType,
) -> IndexKit:
    return IndexKit(
        identifier=identifier.strip(),
        name=name.strip(),
        type_id=type.id,
        kit_type_id=KitType.INDEX_KIT.id,
        supported_protocol_ids=supported_protocol_ids,
    )


def search(
    name: str | None = None,
    identifier: str | None = None,
    name_weight: float = 0.5,
    identifier_weight: float = 0.5,
    statement: sql.Select[tuple[IndexKit]] = sa.select(IndexKit),
) -> sql.Select[tuple[IndexKit]]:
    filter_conditions: list[sql.ColumnElement[bool]] = []
    relevance = sa.literal(0.0)

    if name is not None:
        filter_conditions.append(utils.safe_trgm_search(IndexKit.name, name))
        relevance += sa.func.similarity(IndexKit.name, name) * name_weight

    if identifier is not None:
        filter_conditions.append(utils.safe_ilike(IndexKit.identifier, identifier))
        relevance += sa.func.similarity(IndexKit.identifier, identifier) * identifier_weight

    if not filter_conditions:
        return statement

    return (
        statement
        .where(sa.or_(*filter_conditions))
        .order_by(sa.nulls_last(relevance.desc()))
    )


def select(
    id: int | None = None,
    type_in: list[IndexType] | None = None,
    type: IndexType | None = None,
    identifier: str | None = None,
    statement: sql.Select[tuple[IndexKit]] = sa.select(IndexKit),
) -> sql.Select[tuple[IndexKit]]:
    statement = statement.where(IndexKit.kit_type_id == KitType.INDEX_KIT.id)

    if id is not None:
        statement = statement.where(IndexKit.id == id)
    if type_in is not None:
        statement = statement.where(IndexKit.type_id.in_([t.id for t in type_in]))
    if type is not None:
        statement = statement.where(IndexKit.type_id == type.id)
    if identifier is not None:
        statement = statement.where(IndexKit.identifier == identifier.strip())

    return statement
