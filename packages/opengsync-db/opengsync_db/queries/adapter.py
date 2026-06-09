import sqlalchemy as sa

from ..models import Adapter, IndexKit, Barcode


def create(
    index_kit: IndexKit,
    well: str | None = None
) -> Adapter:
    return Adapter(well=well, index_kit=index_kit)


def select(
    id: int | None = None,
    index_kit_id: int | None = None,
    well: str | None = None,
    search_name: str | None = None,
    statement: sa.Select[tuple[Adapter]] = sa.select(Adapter),
) -> sa.Select[tuple[Adapter]]:
    if id is not None:
        statement = statement.where(Adapter.id == id)
    if index_kit_id is not None:
        statement = statement.where(Adapter.index_kit_id == index_kit_id)
    if well is not None:
        statement = statement.where(Adapter.well == well)
    
    if search_name is not None:
        statement = statement.join(
            Barcode,
            Barcode.adapter_id == Adapter.id
        ).order_by(sa.nulls_last(sa.func.similarity(Barcode.name,search_name).desc())).distinct(Adapter.id)
    return statement