from collections.abc import Iterator

import pandas as pd
from pydantic import BaseModel

from opengsync_db import categories as C, models, queries as Q

from ....components import inputs
from ....components.tables import DuplicateCellValue, MissingCellValue, TextColumn
from ....utils import parsing
from .EditKitBarcodes import EditKitBarcodesForm


class EditCombinatorialKitBarcodes(EditKitBarcodesForm):
    rc_sequence_i7 = inputs.boolean.SwitchInputField("Reverse Complement i7")
    rc_sequence_i5 = inputs.boolean.SwitchInputField("Reverse Complement i5")
    reverse_complement_fields = ("rc_sequence_i7", "rc_sequence_i5")

    class RowSchema(BaseModel):
        name_i7: str | None = None
        sequence_i7: str | None = None
        name_i5: str | None = None
        sequence_i5: str | None = None

    def __init__(self, index_kit: models.IndexKit) -> None:
        super().__init__(index_kit)
        clean = self._clean
        for name, label, length, required in (
            ("name_i7", "Name i7", models.LibraryIndex.name_i7.type.length, False),
            ("sequence_i7", "Sequence i7", models.LibraryIndex.sequence_i7.type.length, False),
            ("name_i5", "Name i5", models.LibraryIndex.name_i5.type.length, False),
            ("sequence_i5", "Sequence i5", models.LibraryIndex.sequence_i5.type.length, False),
        ):
            keep = ".-_" if name.startswith("name") else ""
            self.spreadsheet.add_column(TextColumn(name, label, 200, max_length=length, required=required, clean_up_fnc=lambda value, keep=keep: clean(value, keep=keep, spaces="")))

    def validate_barcodes(self, df: pd.DataFrame) -> None:
        duplicate_pair = df.duplicated(["sequence_i7", "sequence_i5"], keep=False)
        for idx, row in parsing.safe_iter(df, self.RowSchema, int):
            if (row.name_i7 is None) != (row.sequence_i7 is None):
                missing_column = "sequence_i7" if row.name_i7 is not None else "name_i7"
                self.spreadsheet.add_error(idx, missing_column, MissingCellValue("Name and sequence i7 must be provided together."))
            if (row.name_i5 is None) != (row.sequence_i5 is None):
                missing_column = "sequence_i5" if row.name_i5 is not None else "name_i5"
                self.spreadsheet.add_error(idx, missing_column, MissingCellValue("Name and sequence i5 must be provided together."))
            if duplicate_pair.at[idx]:
                for column in ("sequence_i7", "sequence_i5"):
                    self.spreadsheet.add_error(idx, column, DuplicateCellValue("Duplicate sequence combination i7 & i5."))
        self._validate_name_sequence_consistency(df, "i7")
        self._validate_name_sequence_consistency(df, "i5")

    def barcode_rows(self, df: pd.DataFrame) -> Iterator[tuple[models.Adapter, list[dict]]]:
        for _, row in parsing.safe_iter(df, self.RowSchema):
            for index, barcode_type, name, sequence in (
                ("i7", C.BarcodeType.INDEX_I7, row.name_i7, row.sequence_i7),
                ("i5", C.BarcodeType.INDEX_I5, row.name_i5, row.sequence_i5),
            ):
                if name is None or sequence is None:
                    continue
                if getattr(self, f"rc_sequence_{index}").data:
                    sequence = models.Barcode.reverse_complement(sequence)
                adapter = Q.adapter.create(index_kit=self.index_kit, well=None)
                yield adapter, [{"name": name, "sequence": sequence, "well": None, "type": barcode_type}]
