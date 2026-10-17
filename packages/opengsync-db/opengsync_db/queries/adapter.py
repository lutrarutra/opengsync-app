import sqlalchemy as sa

from ..models import Adapter, IndexKit, Barcode
from ..core import utils


def create(
    index_kit: IndexKit,
    well: str | None = None
) -> Adapter:
    return Adapter(well=well, index_kit=index_kit)


def search(
    name: str | None = None,
    statement: sa.Select[tuple[Adapter]] = sa.select(Adapter),
) -> sa.Select[tuple[Adapter]]:
    if name is None:
        return statement
    return (
        statement
        .join(Barcode, Barcode.adapter_id == Adapter.id)
        .where(utils.safe_trgm_search(Barcode.name, name))
        .order_by(sa.nulls_last(sa.func.similarity(Barcode.name, name).desc()))
        .distinct(Adapter.id)
    )


def select(
    id: int | None = None,
    index_kit_id: int | None = None,
    well: str | None = None,
    statement: sa.Select[tuple[Adapter]] = sa.select(Adapter),
) -> sa.Select[tuple[Adapter]]:
    if id is not None:
        statement = statement.where(Adapter.id == id)
    if index_kit_id is not None:
        statement = statement.where(Adapter.index_kit_id == index_kit_id)
    if well is not None:
        statement = statement.where(Adapter.well == well)
    return statement