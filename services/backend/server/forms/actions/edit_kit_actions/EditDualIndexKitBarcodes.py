from collections.abc import Iterator

import pandas as pd
from pydantic import BaseModel

from opengsync_db import categories as C, models, queries as Q

from ....components import inputs
from ....components.tables import DuplicateCellValue, MissingCellValue, TextColumn
from ....utils import parsing
from .EditKitBarcodes import EditKitBarcodesForm


class EditDualIndexKitBarcodes(EditKitBarcodesForm):
    rc_sequence_i7 = inputs.boolean.SwitchInputField("Reverse Complement i7")
    rc_sequence_i5 = inputs.boolean.SwitchInputField("Reverse Complement i5")
    reverse_complement_fields = ("rc_sequence_i7", "rc_sequence_i5")

    class RowSchema(BaseModel):
        well: str | None = None
        name_i7: str | None = None
        sequence_i7: str | None = None
        name_i5: str | None = None
        sequence_i5: str | None = None

    def __init__(self, index_kit: models.IndexKit) -> None:
        super().__init__(index_kit)
        clean = self._clean
        self.spreadsheet.add_column(TextColumn("well", "Well", 100, max_length=models.Adapter.well.type.length, clean_up_fnc=lambda value: clean(value, spaces="")))
        self.spreadsheet.add_column(TextColumn("name_i7", "Name i7", 150, max_length=models.LibraryIndex.name_i7.type.length, clean_up_fnc=lambda value: clean(value, keep=".-_", spaces="")))
        self.spreadsheet.add_column(TextColumn("sequence_i7", "Sequence i7", 200, max_length=models.LibraryIndex.sequence_i7.type.length, clean_up_fnc=lambda value: clean(value, spaces="")))
        self.spreadsheet.add_column(TextColumn("name_i5", "Name i5", 150, max_length=models.LibraryIndex.name_i5.type.length, required=False, clean_up_fnc=lambda value: clean(value, keep=".-_", spaces="")))
        self.spreadsheet.add_column(TextColumn("sequence_i5", "Sequence i5", 200, max_length=models.LibraryIndex.sequence_i5.type.length, clean_up_fnc=lambda value: clean(value, spaces="")))

    def validate_barcodes(self, df: pd.DataFrame) -> None:
        self._normalize_wells(df)
        df.loc[df["name_i5"].isna(), "name_i5"] = df.loc[df["name_i5"].isna(), "name_i7"]
        duplicate_pair = df.duplicated(["sequence_i7", "sequence_i5"], keep=False)
        duplicate_well = df.duplicated("well", keep=False)
        for idx, row in parsing.safe_iter(df, self.RowSchema, int):
            if row.well is None:
                self.spreadsheet.add_error(idx, "well", MissingCellValue("Well is missing."))
            elif duplicate_well.at[idx]:
                self.spreadsheet.add_error(idx, "well", DuplicateCellValue("Duplicate well."))
            for column, label, value in (
                ("name_i7", "Name i7", row.name_i7),
                ("sequence_i7", "Sequence i7", row.sequence_i7),
                ("name_i5", "Name i5", row.name_i5),
                ("sequence_i5", "Sequence i5", row.sequence_i5),
            ):
                if value is None:
                    self.spreadsheet.add_error(idx, column, MissingCellValue(f"{label} is missing."))
            if duplicate_pair.at[idx]:
                for column in ("sequence_i7", "sequence_i5"):
                    self.spreadsheet.add_error(idx, column, DuplicateCellValue("Duplicate sequence combination i7 & i5."))
        self._validate_name_sequence_consistency(df, "i7")
        self._validate_name_sequence_consistency(df, "i5")
        self.spreadsheet.set_data(df)

    def barcode_rows(self, df: pd.DataFrame) -> Iterator[tuple[models.Adapter, list[dict]]]:
        class PersistRow(BaseModel):
            well: str
            name_i7: str
            sequence_i7: str
            name_i5: str
            sequence_i5: str

        for _, row in parsing.safe_iter(df, PersistRow):
            sequence_i7 = models.Barcode.reverse_complement(row.sequence_i7) if self.rc_sequence_i7.data else row.sequence_i7
            sequence_i5 = models.Barcode.reverse_complement(row.sequence_i5) if self.rc_sequence_i5.data else row.sequence_i5
            adapter = Q.adapter.create(index_kit=self.index_kit, well=row.well)
            yield adapter, [
                {"name": row.name_i7, "sequence": sequence_i7, "well": row.well, "type": C.BarcodeType.INDEX_I7},
                {"name": row.name_i5, "sequence": sequence_i5, "well": row.well, "type": C.BarcodeType.INDEX_I5},
            ]
