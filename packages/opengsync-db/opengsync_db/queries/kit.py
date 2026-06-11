import sqlalchemy as sa

from ..models import Kit, Protocol, links
from ..categories import KitType


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


def select(
    id: int | None = None,
    name: str | None = None,
    identifier: str | None = None,
    type: KitType | None = None,
    type_in: list[KitType] | None = None,
    protocol: Protocol | None = None,
    not_in_protocol: Protocol | None = None,
    protocol_id: int | None = None,
    search_name: str | None = None,
    search_identifier: str | None = None,
    search_identifier_name: str | None = None,
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

    if protocol is not None:
        statement = statement.where(
            sa.select(1).where(
                (links.ProtocolKitLink.protocol_id == protocol.id) &
                (links.ProtocolKitLink.kit_id == Kit.id)
            ).correlate_except(links.ProtocolKitLink).exists()
        )
    elif protocol_id is not None:
        statement = statement.where(
            sa.select(1).where(
                (links.ProtocolKitLink.protocol_id == protocol_id) &
                (links.ProtocolKitLink.kit_id == Kit.id)
            ).correlate_except(links.ProtocolKitLink).exists()
        )
    if not_in_protocol is not None:
        statement = statement.where(
            ~sa.select(1).where(
                (links.ProtocolKitLink.protocol_id == not_in_protocol.id) &
                (links.ProtocolKitLink.kit_id == Kit.id)
            ).correlate_except(links.ProtocolKitLink).exists()
        )

    if search_name is not None:
        statement = statement.order_by(sa.nulls_last(sa.func.similarity(Kit.name, search_name).desc()))
    elif search_identifier is not None:
        statement = statement.order_by(sa.nulls_last(sa.func.similarity(Kit.identifier, search_identifier).desc()))
    elif search_identifier_name is not None:
        statement = statement.order_by(sa.nulls_last(sa.func.similarity(
            Kit.identifier + ' ' + Kit.name, search_identifier_name
        ).desc()))
    return statement
