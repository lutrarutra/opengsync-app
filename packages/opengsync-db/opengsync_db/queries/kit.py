import sqlalchemy as sa

from ..models import Kit, Protocol, links
from ..categories import KitType
from ..core import utils


def create(
    name: str,
    identifier: str,
    kit_type: KitType = KitType.LIBRARY_KIT,
) -> Kit:
    return Kit(
        name=name,
        identifier=identifier,
        kit_type_id=kit_type.id,
    )


def search(
    name: str | None = None,
    identifier: str | None = None,
    name_weight: float = 0.5,
    identifier_weight: float = 0.5,
    statement: sa.Select[tuple[Kit]] = sa.select(Kit),
) -> sa.Select[tuple[Kit]]:
    filter_conditions: list[sa.ColumnElement[bool]] = []
    relevance = sa.literal(0.0)

    if name is not None:
        filter_conditions.append(utils.safe_trgm_search(Kit.name, name))
        relevance += sa.func.similarity(Kit.name, name) * name_weight

    if identifier is not None:
        filter_conditions.append(utils.safe_ilike(Kit.identifier, identifier))
        relevance += sa.func.similarity(Kit.identifier, identifier) * identifier_weight

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
    type: KitType | None = None,
    type_in: list[KitType] | None = None,
    protocol_id: int | None = None,
    not_in_protocol_id: int | None = None,
    statement: sa.Select[tuple[Kit]] = sa.select(Kit),
) -> sa.Select[tuple[Kit]]:
    if id is not None:
        statement = statement.where(Kit.id == id)
    if name is not None:
        statement = statement.where(Kit.name == name)
    if identifier is not None:
        statement = statement.where(Kit.identifier == identifier)

    if type is not None:
        statement = statement.where(Kit.kit_type_id == type.id)

    if type_in is not None:
        statement = statement.where(Kit.kit_type_id.in_([t.id for t in type_in]))

    if protocol_id is not None:
        statement = statement.where(
            sa.select(1).where(
                (links.ProtocolKitLink.protocol_id == protocol_id) &
                (links.ProtocolKitLink.kit_id == Kit.id)
            ).correlate_except(links.ProtocolKitLink).exists()
        )
    if not_in_protocol_id is not None:
        statement = statement.where(
            ~sa.select(1).where(
                (links.ProtocolKitLink.protocol_id == not_in_protocol_id) &
                (links.ProtocolKitLink.kit_id == Kit.id)
            ).correlate_except(links.ProtocolKitLink).exists()
        )
    return statement
