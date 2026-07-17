import sqlalchemy as sa

from ..models import Protocol
from ..categories import ServiceType
from ..core import utils


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


def search(
    name: str | None = None,
    statement: sa.Select[tuple[Protocol]] = sa.select(Protocol),
) -> sa.Select[tuple[Protocol]]:
    if name is not None:
        statement = statement.where(
            utils.safe_trgm_search(Protocol.name, name)
        ).order_by(sa.nulls_last(sa.func.similarity(Protocol.name, name).desc()))
    return statement


def select(
    id: int | None = None,
    name: str | None = None,
    service_type: ServiceType | None = None,
    service_type_in: list[ServiceType] | None = None,
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
    return statement