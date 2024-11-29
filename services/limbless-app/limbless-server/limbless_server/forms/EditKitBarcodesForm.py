from typing import Optional

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import BooleanField

from limbless_db import models
from limbless_db.categories import IndexType, BarcodeType

from .. import db, logger  # noqa
from ..tools import SpreadSheetColumn, tools
from .HTMXFlaskForm import HTMXFlaskForm
from .SpreadsheetInput import SpreadsheetInput


class EditKitBarcodesForm(HTMXFlaskForm):
    _template_path = "forms/edit_kit_barcodes.html"

    rc_sequence_i7 = BooleanField("Reverse Complement i7", default=False)
    rc_sequence_i5 = BooleanField("Reverse Complement i5", default=False)

    dual_index_columns = [
        SpreadSheetColumn("well", "Well", "text", 100, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("name_i7", "Name i7", "text", 150, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, replace_white_spaces_with="")),
        SpreadSheetColumn("sequence_i7", "Sequence i7", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("name_i5", "Name i5", "text", 150, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, replace_white_spaces_with="")),
        SpreadSheetColumn("sequence_i5", "Sequence i5", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    ]

    single_index_columns = [
        SpreadSheetColumn("well", "Well", "text", 100, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("name", "Name", "text", 150, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, replace_white_spaces_with="")),
        SpreadSheetColumn("sequence", "Sequence", "text", 300, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    ]

    tenx_atac_index_columns = [
        SpreadSheetColumn("well", "Well", "text", 100, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("name", "Name", "text", 150, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, replace_white_spaces_with="")),
        SpreadSheetColumn("sequence_2", "Sequence 2", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("sequence_1", "Sequence 1", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("sequence_3", "Sequence 3", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("sequence_4", "Sequence 4", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    ]

    def __init__(self, index_kit: models.IndexKit, formdata: Optional[dict] = None):
        super().__init__(formdata=formdata)
        self.index_kit = index_kit
        self._context["index_kit"] = index_kit

        if self.index_kit.type == IndexType.DUAL_INDEX:
            self.columns = self.dual_index_columns
        elif self.index_kit.type == IndexType.SINGLE_INDEX:
            self.columns = self.single_index_columns
        elif self.index_kit.type == IndexType.TENX_ATAC_INDEX:
            self.columns = self.tenx_atac_index_columns

        if formdata is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        else:
            csrf_token = formdata.get("csrf_token")

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=csrf_token,
            post_url="", formdata=formdata, df=self.__fill_form(),
            allow_new_rows=True
        )

    def __fill_form(self):
        barcodes = db.get_index_kit_barcodes_df(self.index_kit.id)

        if self.index_kit.type == IndexType.TENX_ATAC_INDEX:
            barcode_data = {
                "well": [],
                "index_name": [],
                "sequence_1": [],
                "sequence_2": [],
                "sequence_3": [],
                "sequence_4": [],
            }
            for _, row in barcodes.iterrows():
                barcode_data["well"].append(row["well"])
                barcode_data["index_name"].append(row["names"][0])
                for i in range(4):
                    barcode_data[f"sequence_{i + 1}"].append(row["sequences"][i])
        elif self.index_kit.type == IndexType.DUAL_INDEX:
            barcode_data = {
                "well": [],
                "name_i7": [],
                "sequence_i7": [],
                "name_i5": [],
                "sequence_i5": [],
            }
            for _, row in barcodes.iterrows():
                barcode_data["well"].append(row["well"])
                for i in range(2):
                    if row["types"][i] == BarcodeType.INDEX_I7:
                        barcode_data["name_i7"].append(row["names"][i])
                        barcode_data["sequence_i7"].append(row["sequences"][i])
                    else:
                        barcode_data["name_i5"].append(row["names"][i])
                        barcode_data["sequence_i5"].append(row["sequences"][i])
        elif self.index_kit.type == IndexType.SINGLE_INDEX:
            barcode_data = {
                "well": [],
                "name": [],
                "sequence": [],
            }
            for _, row in barcodes.iterrows():
                barcode_data["well"].append(row["well"])
                barcode_data["name"].append(row["names"][0])
                barcode_data["sequence"].append(row["sequences"][0])

        return pd.DataFrame(barcode_data)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        duplicate_well = df.duplicated(subset="well", keep=False)

        if self.index_kit.type == IndexType.DUAL_INDEX:
            df.loc[df["name_i5"].isna(), "name_i5"] = df.loc[df["name_i5"].isna(), "name_i7"]

        for i, (idx, row) in enumerate(df.iterrows()):
            if row["well"] is None:
                self.spreadsheet.add_error(i + 1, "well", "Well is missing.", "missing_value")
            elif duplicate_well.at[idx]:
                self.spreadsheet.add_error(i + 1, "well", "Duplicate well.", "duplicate_value")

            if self.index_kit.type == IndexType.DUAL_INDEX:
                if row["name_i7"] is None:
                    self.spreadsheet.add_error(i + 1, "name_i7", "Name i7 is missing.", "missing_value")
                if row["sequence_i7"] is None:
                    self.spreadsheet.add_error(i + 1, "sequence_i7", "Sequence i7 is missing.", "missing_value")
                if row["name_i5"] is None:
                    self.spreadsheet.add_error(i + 1, "name_i5", "Name i5 is missing.", "missing_value")
                if row["sequence_i5"] is None:
                    self.spreadsheet.add_error(i + 1, "sequence_i5", "Sequence i5 is missing.", "missing_value")

                if (row["name_i7"] == df["name_i7"]).sum() > 1:
                    self.spreadsheet.add_error(i + 1, "name_i7", "Duplicate name i7.", "duplicate_value")
                if (row["sequence_i7"] == df["sequence_i7"]).sum() > 1:
                    self.spreadsheet.add_error(i + 1, "sequence_i7", "Duplicate sequence i7.", "duplicate_value")
                if (row["name_i5"] == df["name_i5"]).sum() > 1:
                    self.spreadsheet.add_error(i + 1, "name_i5", "Duplicate name i5.", "duplicate_value")
                if (row["sequence_i5"] == df["sequence_i5"]).sum() > 1:
                    self.spreadsheet.add_error(i + 1, "sequence_i5", "Duplicate sequence i5.", "duplicate_value")

            elif self.index_kit.type == IndexType.SINGLE_INDEX:
                if row["name"] is None:
                    self.spreadsheet.add_error(i + 1, "name", "Name is missing.", "missing_value")
                if row["sequence"] is None:
                    self.spreadsheet.add_error(i + 1, "sequence", "Sequence is missing.", "missing_value")
                
                if (row["name"] == df["name"]).sum() > 1:
                    self.spreadsheet.add_error(i + 1, "name", "Duplicate name.", "duplicate_value")
                if (row["sequence"] == df["sequence"]).sum() > 1:
                    self.spreadsheet.add_error(i + 1, "sequence", "Duplicate sequence.", "duplicate_value")
            
            elif self.index_kit.type == IndexType.TENX_ATAC_INDEX:
                if row["name"] is None:
                    self.spreadsheet.add_error(i + 1, "name", "Name is missing.", "missing_value")
                if row["sequence_1"] is None:
                    self.spreadsheet.add_error(i + 1, "sequence_1", "Sequence 1 is missing.", "missing_value")
                if row["sequence_2"] is None:
                    self.spreadsheet.add_error(i + 1, "sequence_2", "Sequence 2 is missing.", "missing_value")
                if row["sequence_3"] is None:
                    self.spreadsheet.add_error(i + 1, "sequence_3", "Sequence 3 is missing.", "missing_value")
                if row["sequence_4"] is None:
                    self.spreadsheet.add_error(i + 1, "sequence_4", "Sequence 4 is missing.", "missing_value")

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.index_kit = db.remove_all_barcodes_from_kit(self.index_kit.id)

        for idx, row in self.df.iterrows():
            if self.index_kit.type == IndexType.DUAL_INDEX:
                adapter = db.create_adapter(
                    index_kit_id=self.index_kit.id,
                    well=row["well"],
                )
                db.create_barcode(
                    name=row["name_i7"],
                    sequence=row["sequence_i7"] if not self.rc_sequence_i7.data else models.Barcode.reverse_complement(row["sequence_i7"]),
                    well=row["well"],
                    adapter_id=adapter.id,
                    type=BarcodeType.INDEX_I7,
                )
                db.create_barcode(
                    name=row["name_i5"],
                    sequence=row["sequence_i5"] if not self.rc_sequence_i5.data else models.Barcode.reverse_complement(row["sequence_i5"]),
                    well=row["well"],
                    adapter_id=adapter.id,
                    type=BarcodeType.INDEX_I5,
                )
            elif self.index_kit.type == IndexType.SINGLE_INDEX:
                adapter = db.create_adapter(
                    index_kit_id=self.index_kit.id,
                    well=row["well"],
                )
                db.create_barcode(
                    name=row["name"],
                    sequence=row["sequence"] if not self.rc_sequence_i7.data else models.Barcode.reverse_complement(row["sequence"]),
                    well=row["well"],
                    adapter_id=adapter.id,
                    type=BarcodeType.INDEX_I7,
                )

            elif self.index_kit.type == IndexType.TENX_ATAC_INDEX:
                adapter = db.create_adapter(
                    index_kit_id=self.index_kit.id,
                    well=row["well"],
                )
                for i in range(4):
                    db.create_barcode(
                        name=row["name"],
                        sequence=row[f"sequence_{i + 1}"] if not self.rc_sequence_i7.data else models.Barcode.reverse_complement(row[f"sequence_{i + 1}"]),
                        well=row["well"],
                        adapter_id=adapter.id,
                        type=BarcodeType.INDEX_I7,
                    )
        
        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("kits_page.index_kit_page", index_kit_id=self.index_kit.id)))
        
