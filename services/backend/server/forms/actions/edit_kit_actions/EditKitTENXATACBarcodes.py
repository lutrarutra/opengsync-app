from collections.abc import Iterator

import pandas as pd
from pydantic import BaseModel

from opengsync_db import categories as C, models, queries as Q

from ....components import inputs
from ....components.tables import DuplicateCellValue, MissingCellValue, TextColumn
from ....utils import parsing
from .EditKitBarcodes import EditKitBarcodesForm


class EditKitTENXATACBarcodes(EditKitBarcodesForm):
    rc_sequence = inputs.boolean.SwitchInputField("Reverse Complement Sequences")
    reverse_complement_fields = ("rc_sequence",)

    class RowSchema(BaseModel):
        well: str | None = None
        name: str | None = None
        sequence_1: str | None = None
        sequence_2: str | None = None
        sequence_3: str | None = None
        sequence_4: str | None = None

    def __init__(self, index_kit: models.IndexKit) -> None:
        super().__init__(index_kit)
        clean = self._clean
        self.spreadsheet.add_column(TextColumn("well", "Well", 100, max_length=models.Adapter.well.type.length, clean_up_fnc=lambda value: clean(value, spaces="")))
        self.spreadsheet.add_column(TextColumn("name", "Name", 150, max_length=models.LibraryIndex.name_i7.type.length, clean_up_fnc=lambda value: clean(value, keep=".-_", spaces="")))
        for index in (1, 2, 3, 4):
            self.spreadsheet.add_column(TextColumn(f"sequence_{index}", f"Sequence {index}", 200, max_length=models.LibraryIndex.sequence_i7.type.length, clean_up_fnc=lambda value: clean(value, spaces="")))

    def validate_barcodes(self, df: pd.DataFrame) -> None:
        self._normalize_wells(df)
        duplicate_well = df.duplicated("well", keep=False)
        for idx, row in parsing.safe_iter(df, self.RowSchema, int):
            if row.well is None:
                self.spreadsheet.add_error(idx, "well", MissingCellValue("Well is missing."))
            elif duplicate_well.at[idx]:
                self.spreadsheet.add_error(idx, "well", DuplicateCellValue("Duplicate well."))
            for column, value in (
                ("name", row.name),
                ("sequence_1", row.sequence_1),
                ("sequence_2", row.sequence_2),
                ("sequence_3", row.sequence_3),
                ("sequence_4", row.sequence_4),
            ):
                if value is None:
                    self.spreadsheet.add_error(idx, column, MissingCellValue(f"{column.replace('_', ' ').title()} is missing."))

    def barcode_rows(self, df: pd.DataFrame) -> Iterator[tuple[models.Adapter, list[dict]]]:
        class PersistRow(BaseModel):
            well: str
            name: str
            sequence_1: str
            sequence_2: str
            sequence_3: str
            sequence_4: str

        for _, row in parsing.safe_iter(df, PersistRow):
            barcode_rows = []
            for sequence in (row.sequence_1, row.sequence_2, row.sequence_3, row.sequence_4):
                if self.rc_sequence.data:
                    sequence = models.Barcode.reverse_complement(sequence)
                barcode_rows.append({"name": row.name, "sequence": sequence, "well": row.well, "type": C.BarcodeType.INDEX_I7})
            yield Q.adapter.create(index_kit=self.index_kit, well=row.well), barcode_rows
