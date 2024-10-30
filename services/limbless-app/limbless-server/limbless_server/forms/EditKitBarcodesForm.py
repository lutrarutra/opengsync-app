import json
from typing import Optional, Literal

import pandas as pd
import numpy as np

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import StringField, BooleanField
from wtforms.validators import DataRequired

from limbless_db import models
from limbless_db.categories import IndexType, BarcodeType

from .. import db, logger  # noqa
from ..tools import SpreadSheetColumn, tools
from .HTMXFlaskForm import HTMXFlaskForm


class EditKitBarcodesForm(HTMXFlaskForm):
    _template_path = "forms/edit_kit_barcodes.html"
    _form_label = "form"

    spreadsheet = StringField("Spreadsheet", validators=[DataRequired()])
    rc_sequence_i7 = BooleanField("Reverse Complement i7", default=False)
    rc_sequence_i5 = BooleanField("Reverse Complement i5", default=False)

    dual_index_columns = {
        "well": SpreadSheetColumn("A", "well", "Well", "text", 100, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        "name_i7": SpreadSheetColumn("B", "name_i7", "Name i7", "text", 150, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, replace_white_spaces_with="")),
        "sequence_i7": SpreadSheetColumn("C", "sequence_i7", "Sequence i7", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        "name_i5": SpreadSheetColumn("D", "name_i5", "Name i5", "text", 150, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, replace_white_spaces_with="")),
        "sequence_i5": SpreadSheetColumn("E", "sequence_i5", "Sequence i5", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    }

    single_index_columns = {
        "well": SpreadSheetColumn("A", "well", "Well", "text", 100, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        "name": SpreadSheetColumn("B", "name", "Name", "text", 150, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, replace_white_spaces_with="")),
        "sequence": SpreadSheetColumn("C", "sequence", "Sequence", "text", 300, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    }

    tenx_atac_index_columns = {
        "well": SpreadSheetColumn("A", "well", "Well", "text", 100, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        "name": SpreadSheetColumn("B", "name", "Name", "text", 150, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, replace_white_spaces_with="")),
        "sequence_2": SpreadSheetColumn("D", "sequence_2", "Sequence 2", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        "sequence_1": SpreadSheetColumn("C", "sequence_1", "Sequence 1", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        "sequence_3": SpreadSheetColumn("E", "sequence_3", "Sequence 3", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        "sequence_4": SpreadSheetColumn("F", "sequence_4", "Sequence 4", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    }

    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
        "invalid_input": "#AED6F1"
    }

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

        self._context["columns"] = self.columns.values()
        self.spreadsheet_style = {}

        if formdata is None:
            self.__fill_form()

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

        df = pd.DataFrame(barcode_data)
        if len(df) > 0:
            self.spreadsheet.data = json.dumps(df.replace(np.nan, "").values.tolist())

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.data:
            self.spreadsheet.errors = ("No data provided.",)
            return False

        if not (data := json.loads(self.spreadsheet.data)):
            self.spreadsheet.errors = ("No data provided.",)
            return False
        
        try:
            df = pd.DataFrame(data)
        except ValueError as e:
            self.spreadsheet.errors = (str(e),)
            return False
        
        df = df.replace(r'^\s*$', None, regex=True)
        df = df.dropna(how="all")
        df.columns = list(self.columns.keys())

        for label, column in self.columns.items():
            if column.clean_up_fnc is not None:
                df[label] = df[label].apply(column.clean_up_fnc)

        errors = []

        def add_error(row_num: int, column: str, message: str, color: Literal["missing_value", "invalid_value", "duplicate_value", "invalid_input"]):
            self.spreadsheet_style[f"{self.columns[column].column}{row_num}"] = f"background-color: {EditKitBarcodesForm.colors[color]};"
            error = f"Row {row_num}: {message}"
            if error not in errors:
                errors.append(error)
            self.spreadsheet.errors = errors

        duplicate_well = df.duplicated(subset="well", keep=False)

        if self.index_kit.type == IndexType.DUAL_INDEX:
            df.loc[df["name_i5"].isna(), "name_i5"] = df.loc[df["name_i5"].isna(), "name_i7"]

        for i, (idx, row) in enumerate(df.iterrows()):
            if row["well"] is None:
                add_error(i + 1, "well", "Well is missing.", "missing_value")
            elif duplicate_well.at[idx]:
                add_error(i + 1, "well", "Duplicate well.", "duplicate_value")

            if self.index_kit.type == IndexType.DUAL_INDEX:
                if row["name_i7"] is None:
                    add_error(i + 1, "name_i7", "Name i7 is missing.", "missing_value")
                if row["sequence_i7"] is None:
                    add_error(i + 1, "sequence_i7", "Sequence i7 is missing.", "missing_value")
                if row["name_i5"] is None:
                    add_error(i + 1, "name_i5", "Name i5 is missing.", "missing_value")
                if row["sequence_i5"] is None:
                    add_error(i + 1, "sequence_i5", "Sequence i5 is missing.", "missing_value")

                if (row["name_i7"] == df["name_i7"]).sum() > 1:
                    add_error(i + 1, "name_i7", "Duplicate name i7.", "duplicate_value")
                if (row["sequence_i7"] == df["sequence_i7"]).sum() > 1:
                    add_error(i + 1, "sequence_i7", "Duplicate sequence i7.", "duplicate_value")
                if (row["name_i5"] == df["name_i5"]).sum() > 1:
                    add_error(i + 1, "name_i5", "Duplicate name i5.", "duplicate_value")
                if (row["sequence_i5"] == df["sequence_i5"]).sum() > 1:
                    add_error(i + 1, "sequence_i5", "Duplicate sequence i5.", "duplicate_value")

            elif self.index_kit.type == IndexType.SINGLE_INDEX:
                if row["name"] is None:
                    add_error(i + 1, "name", "Name is missing.", "missing_value")
                if row["sequence"] is None:
                    add_error(i + 1, "sequence", "Sequence is missing.", "missing_value")
                
                if (row["name"] == df["name"]).sum() > 1:
                    add_error(i + 1, "name", "Duplicate name.", "duplicate_value")
                if (row["sequence"] == df["sequence"]).sum() > 1:
                    add_error(i + 1, "sequence", "Duplicate sequence.", "duplicate_value")
            
            elif self.index_kit.type == IndexType.TENX_ATAC_INDEX:
                if row["name"] is None:
                    add_error(i + 1, "name", "Name is missing.", "missing_value")
                if row["sequence_1"] is None:
                    add_error(i + 1, "sequence_1", "Sequence 1 is missing.", "missing_value")
                if row["sequence_2"] is None:
                    add_error(i + 1, "sequence_2", "Sequence 2 is missing.", "missing_value")
                if row["sequence_3"] is None:
                    add_error(i + 1, "sequence_3", "Sequence 3 is missing.", "missing_value")
                if row["sequence_4"] is None:
                    add_error(i + 1, "sequence_4", "Sequence 4 is missing.", "missing_value")

        if self.spreadsheet.errors:
            self._context["spreadsheet_style"] = self.spreadsheet_style
            self.spreadsheet.data = json.dumps(df.replace(np.nan, "").values.tolist())
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
        
