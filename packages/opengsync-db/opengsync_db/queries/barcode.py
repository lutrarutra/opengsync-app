import sqlalchemy as sa

from ..models import Barcode, Adapter
from ..categories import BarcodeType


def create(
    name: str,
    sequence: str,
    well: str | None,
    type: BarcodeType,
    adapter: Adapter
) -> Barcode:
    return Barcode(
        name=name.strip(),
        sequence=sequence.strip(),
        well=well,
        type_id=type.id,
        adapter=adapter,
        index_kit=adapter.index_kit
    )


def select(
    id: int | None = None,
    index_kit_id: int | None = None,
    adapter_id: int | None = None,
    type: BarcodeType | None = None,
    search_sequence: str | None = None,
    statement: sa.Select[tuple[Barcode]] = sa.select(Barcode),
) -> sa.Select[tuple[Barcode]]:
    if id is not None:
        statement = statement.where(Barcode.id == id)
    if index_kit_id is not None:
        statement = statement.where(Barcode.index_kit_id == index_kit_id)
    if type is not None:
        statement = statement.where(Barcode.type_id == type.id)
    if adapter_id is not None:
        statement = statement.where(Barcode.adapter_id == adapter_id)

    if search_sequence is not None:
        statement = statement.where(Barcode.sequence.ilike(f"%{search_sequence}%"))
    return statement