import sqlalchemy as sa
from sqlalchemy import sql

from ..models import IndexKit
from ..categories import IndexType, KitType


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


def select(
    id: int | None = None,
    type_in: list[IndexType] | None = None,
    index_type: IndexType | None = None,
    search_name: str | None = None,
    search_identifier: str | None = None,
    search_identifier_name: str | None = None,
    statement: sql.Select[tuple[IndexKit]] = sa.select(IndexKit),
) -> sql.Select[tuple[IndexKit]]:
    statement = statement.where(IndexKit.kit_type_id == KitType.INDEX_KIT.id)

    if id is not None:
        statement = statement.where(IndexKit.id == id)

    if type_in is not None:
        statement = statement.where(IndexKit.type_id.in_([t.id for t in type_in]))

    if index_type is not None:
        statement = statement.where(IndexKit.type_id == index_type.id)

    if search_name is not None:
        statement = statement.order_by(sa.nulls_last(sa.func.similarity(IndexKit.name, search_name).desc()))
    elif search_identifier is not None:
        statement = statement.order_by(sa.nulls_last(sa.func.similarity(IndexKit.identifier, search_identifier).desc()))
    elif search_identifier_name is not None:
        statement = statement.order_by(
            sa.func.similarity(IndexKit.identifier + ' ' + IndexKit.name, search_identifier_name).desc()
        )
    return statement
