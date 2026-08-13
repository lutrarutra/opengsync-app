from collections.abc import Iterator

import pandas as pd
from pydantic import BaseModel

from opengsync_db import categories as C, models, queries as Q, SyncSession

from ....components import inputs
from ....components.tables import DuplicateCellValue, MissingCellValue, TextColumn
from ....utils import parsing
from .EditKitBarcodes import EditKitBarcodesForm


class EditSingleIndexKitBarcodes(EditKitBarcodesForm):
    rc_sequence = inputs.boolean.SwitchInputField("Reverse Complement Sequences")
    reverse_complement_fields = ("rc_sequence",)

    class RowSchema(BaseModel):
        well: str | None = None
        name: str | None = None
        sequence: str | None = None

    def __init__(self, index_kit: models.IndexKit) -> None:
        super().__init__(index_kit)
        clean = self._clean
        self.spreadsheet.add_column(TextColumn("well", "Well", 100, max_length=models.Adapter.well.type.length, clean_up_fnc=lambda value: clean(value, spaces="")))
        self.spreadsheet.add_column(TextColumn("name", "Name", 150, max_length=models.LibraryIndex.name_i7.type.length, clean_up_fnc=lambda value: clean(value, keep=".-_", spaces="")))
        self.spreadsheet.add_column(TextColumn("sequence", "Sequence", 300, max_length=models.LibraryIndex.sequence_i7.type.length, clean_up_fnc=lambda value: clean(value, spaces="")))

    def barcode_table(self, session: SyncSession) -> pd.DataFrame:
        df = super().barcode_table(session)
        return df.rename(columns={"sequence_i7": "sequence", "name_i7": "name"})

    def validate_barcodes(self, df: pd.DataFrame) -> None:
        self._normalize_wells(df)
        duplicates = {column: df.duplicated(column, keep=False) for column in ("well", "name", "sequence")}
        for idx, row in parsing.safe_iter(df, self.RowSchema, int):
            for column, label, value in (("well", "Well", row.well), ("name", "Name", row.name), ("sequence", "Sequence", row.sequence)):
                if value is None:
                    self.spreadsheet.add_error(idx, column, MissingCellValue(f"{label} is missing."))
                elif duplicates[column].at[idx]:
                    self.spreadsheet.add_error(idx, column, DuplicateCellValue(f"Duplicate {column}."))

    def barcode_rows(self, df: pd.DataFrame) -> Iterator[tuple[models.Adapter, list[dict]]]:
        class PersistRow(BaseModel):
            well: str
            name: str
            sequence: str

        for _, row in parsing.safe_iter(df, PersistRow):
            sequence = models.Barcode.reverse_complement(row.sequence) if self.rc_sequence.data else row.sequence
            adapter = Q.adapter.create(index_kit=self.index_kit, well=row.well)
            yield adapter, [{"name": row.name, "sequence": sequence, "well": row.well, "type": C.BarcodeType.INDEX_I7}]
