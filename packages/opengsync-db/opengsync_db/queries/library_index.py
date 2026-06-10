import sqlalchemy as sa

from ..models import LibraryIndex
from ..categories import BarcodeOrientation


def create(
    name_i7: str | None,
    name_i5: str | None,
    sequence_i7: str | None,
    sequence_i5: str | None,
    index_kit_i7_id: int | None,
    index_kit_i5_id: int | None,
    orientation: BarcodeOrientation | None,
    library_id: int,
) -> LibraryIndex:
    return LibraryIndex(
        name_i7=name_i7,
        name_i5=name_i5,
        sequence_i7=sequence_i7,
        sequence_i5=sequence_i5,
        index_kit_i7_id=index_kit_i7_id,
        index_kit_i5_id=index_kit_i5_id,
        library_id=library_id,
        _orientation=orientation.id if orientation else None,
    )


def select(
    id: int | None = None,
    name_i7: str | None = None,
    name_i5: str | None = None,
    sequence_i7: str | None = None,
    sequence_i5: str | None = None,
    index_kit_i7_id: int | None = None,
    index_kit_i5_id: int | None = None,
    library_id: int | None = None,
    statement: sa.Select[tuple[LibraryIndex]] = sa.select(LibraryIndex),
) -> sa.Select[tuple[LibraryIndex]]:
    if id is not None:
        statement = statement.where(LibraryIndex.id == id)
    if name_i7 is not None:
        statement = statement.where(LibraryIndex.name_i7 == name_i7)
    if name_i5 is not None:
        statement = statement.where(LibraryIndex.name_i5 == name_i5)
    if sequence_i7 is not None:
        statement = statement.where(LibraryIndex.sequence_i7 == sequence_i7)
    if sequence_i5 is not None:
        statement = statement.where(LibraryIndex.sequence_i5 == sequence_i5)
    if index_kit_i7_id is not None:
        statement = statement.where(LibraryIndex.index_kit_i7_id == index_kit_i7_id)
    if index_kit_i5_id is not None:
        statement = statement.where(LibraryIndex.index_kit_i5_id == index_kit_i5_id)
    if library_id is not None:
        statement = statement.where(LibraryIndex.library_id == library_id)
    return statement