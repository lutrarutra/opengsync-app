import sqlalchemy as sa

from ..models import Protocol
from ..categories import ServiceType


def create(
    name: str,
    service_type: ServiceType,
    read_structure: str | None = None,
) -> Protocol:
    return Protocol(
        name=name,
        service_type_id=service_type.id,
        read_structure=read_structure,
    )


def select(
    id: int | None = None,
    name: str | None = None,
    service_type: ServiceType | None = None,
    service_type_in: list[ServiceType] | None = None,
    search_name: str | None = None,
    statement: sa.Select[tuple[Protocol]] = sa.select(Protocol),
) -> sa.Select[tuple[Protocol]]:
    if id is not None:
        statement = statement.where(Protocol.id == id)
    if name is not None:
        statement = statement.where(Protocol.name == name)
    if service_type is not None:
        statement = statement.where(Protocol.service_type_id == service_type.id)
    if service_type_in is not None:
        statement = statement.where(Protocol.service_type_id.in_([t.id for t in service_type_in]))
    if search_name is not None:
        statement = statement.order_by(sa.nulls_last(sa.func.similarity(Protocol.name, search_name).desc()))

    return statement