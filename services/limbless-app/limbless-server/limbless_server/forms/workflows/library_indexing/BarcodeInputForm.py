import os
import json
from typing import Optional, Literal

import pandas as pd
import numpy as np

from flask import Response, current_app
from wtforms import SelectField, StringField, FormField
from wtforms.validators import Optional as OptionalValidator
from flask_wtf import FlaskForm

from limbless_db import models

from .... import logger, tools  # noqa F401
from ....tools import SpreadSheetColumn
from ...HTMXFlaskForm import HTMXFlaskForm
from .IndexKitMappingForm import IndexKitMappingForm
from .CompleteLibraryIndexingForm import CompleteLibraryIndexingForm
from ...SearchBar import OptionalSearchBar


class PlateSubForm(FlaskForm):
    index_kit = FormField(OptionalSearchBar, label="Select Index Kit")
    starting_index = SelectField("Starting Index", choices=[(i, models.Plate.well_identifier(i, 12, 8)) for i in range(96)], default=0, coerce=int)


class BarcodeInputForm(HTMXFlaskForm):
    _template_path = "workflows/library_indexing/indexing-1.html"
    _form_label = "library_indexing_form"
    
    columns = {
        "library_id": SpreadSheetColumn("A", "library_id", "ID", "numeric", 50, int),
        "library_name": SpreadSheetColumn("B", "library_name", "Library Name", "text", 250, str),
        "index_well": SpreadSheetColumn("C", "index_well", "Index Well", "text", 100, str),
        "pool": SpreadSheetColumn("D", "pool", "Pool", "text", 100, str),
        "kit_i7": SpreadSheetColumn("E", "kit", "i7 Kit", "text", 200, str),
        "name_i7": SpreadSheetColumn("F", "name_i7", "i7 Name", "text", 200, str),
        "sequence_i7": SpreadSheetColumn("G", "sequence_i7", "i7 Sequence", "text", 200, str),
        "kit_i5": SpreadSheetColumn("H", "kit", "i5 Kit", "text", 200, str),
        "name_i5": SpreadSheetColumn("I", "name_i5", "i5 Name", "text", 200, str),
        "sequence_i5": SpreadSheetColumn("J", "sequence_i5", "i5 Sequence", "text", 200, str),
    }
    
    _mapping: dict[str, str] = dict([(col.name, col.label) for col in columns.values()])
    _required_columns: list[str] = [col.name for col in columns.values()]

    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
        "invalid_input": "#AED6F1"
    }

    spreadsheet_dummy = StringField(validators=[OptionalValidator()])
    plate_form = FormField(PlateSubForm)

    def __init__(self, lab_prep: models.LabPrep, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.lab_prep = lab_prep
        self.library_table = self.get_template()
        self._context["columns"] = BarcodeInputForm.columns.values()
        self._context["colors"] = BarcodeInputForm.colors
        self._context["lab_prep"] = lab_prep
        self._context["active_tab"] = "help"
        self.spreadsheet_style = dict()

    def get_template(self) -> pd.DataFrame:
        if self.lab_prep.prep_file_id is not None:
            prep_table = pd.read_excel(os.path.join(current_app.config["MEDIA_FOLDER"], self.lab_prep.prep_file.path), "prep_table")  # type: ignore
            prep_table = prep_table.dropna(subset=["library_id", "library_name"])
            return prep_table[BarcodeInputForm.columns.keys()].copy()
        
        library_data = dict([(key, []) for key in BarcodeInputForm.columns.keys()])

        for library in self.lab_prep.libraries:
            library_data["library_id"].append(library.id)
            library_data["library_name"].append(library.name)
            library_data["index_well"].append(None)
            library_data["pool"].append(None)
            library_data["kit_i7"].append(None)
            library_data["name_i7"].append(None)
            library_data["sequence_i7"].append(None)
            library_data["kit_i5"].append(None)
            library_data["name_i5"].append(None)
            library_data["sequence_i5"].append(None)

        return pd.DataFrame(library_data)
        
    def prepare(self):
        self._context["spreadsheet_data"] = self.library_table.replace(np.nan, "").values.tolist()

    def validate(self) -> bool:
        validated = super().validate()
            
        if not validated:
            return False
            
        data = json.loads(self.formdata["spreadsheet"])  # type: ignore
        try:
            self.df = pd.DataFrame(data)
        except ValueError as e:
            self.spreadsheet_dummy.errors = (str(e),)
            return False
        
        if len(self.df.columns) != len(list(BarcodeInputForm.columns.keys())):
            self.spreadsheet_dummy.errors = (f"Invalid number of columns (expected {len(BarcodeInputForm.columns)}). Do not insert new columns or rearrange existing columns.",)
            return False
        
        self.df.columns = list(BarcodeInputForm.columns.keys())
        self.df = self.df.replace(r'^\s*$', None, regex=True)
        self.df = self.df.dropna(how="all")

        if len(self.df) == 0:
            self.spreadsheet_dummy.errors = ("Please fill-out spreadsheet.",)
            return False
            
        self.df["sequence_i7"] = self.df["sequence_i7"].apply(lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with=""))
        self.df["sequence_i5"] = self.df["sequence_i5"].apply(lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with=""))

        self.spreadsheet_dummy.errors = []

        def add_error(row_num: int, column: str, message: str, color: Literal["missing_value", "invalid_value", "duplicate_value", "invalid_input"]):
            self.spreadsheet_style[f"{BarcodeInputForm.columns[column].column}{row_num}"] = f"background-color: {BarcodeInputForm.colors[color]};"
            self.spreadsheet_dummy.errors.append(f"Row {row_num}: {message}")  # type: ignore

        kit_defined = self.df["kit_i7"].notna() & (self.df["index_well"].notna() | self.df["name_i7"].notna())
        manual_defined = self.df["sequence_i7"].notna()

        self.df.loc[self.df["kit_i5"].isna(), "kit_i5"] = self.df.loc[self.df["kit_i5"].isna(), "kit_i7"]
        self.df.loc[self.df["name_i5"].isna(), "name_i5"] = self.df.loc[self.df["name_i5"].isna(), "name_i7"]

        for i, (idx, row) in enumerate(self.df.iterrows()):
            if pd.isna(row["library_id"]):
                add_error(i + 1, "library_id", "missing 'library_id'", "missing_value")
            elif row["library_id"] not in self.library_table["library_id"].values:
                add_error(i + 1, "library_id", "invalid 'library_id'", "invalid_value")

            if pd.isna(row["library_name"]):
                add_error(i + 1, "library_name", "missing 'library_name'", "missing_value")
            elif row["library_name"] not in self.library_table["library_name"].values:
                add_error(i + 1, "library_name", "invalid 'library_name'", "invalid_value")

            if not kit_defined.at[idx] and not manual_defined.at[idx]:
                add_error(i + 1, "sequence_i7", "missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'", "missing_value")

        validated = validated and (len(self.spreadsheet_dummy.errors) == 0 and len(self.spreadsheet_style) == 0)

        return validated

    def process_request(self) -> Response:
        if not self.validate():
            self._context["active_tab"] = "spreadsheet"
            self._context["spreadsheet_style"] = self.spreadsheet_style
            self._context["spreadsheet_data"] = self.df[BarcodeInputForm.columns.keys()].replace(np.nan, "").values.tolist()
            if self._context["spreadsheet_data"] == []:
                self._context["spreadsheet_data"] = [[None]]

            return self.make_response()
        
        if self.df["pool"].isna().all():
            self.df["pool"] = "1"

        if self.df["kit_i7"].notna().any():
            index_kit_mapping_form = IndexKitMappingForm()
            index_kit_mapping_form.metadata["lab_prep_id"] = self.lab_prep.id
            index_kit_mapping_form.add_table("library_table", self.df)
            index_kit_mapping_form.update_data()
            index_kit_mapping_form.prepare()
            return index_kit_mapping_form.make_response()
        
        barcode_table_data = {
            "library_id": [],
            "library_name": [],
            "pool": [],
            "sequence_i7": [],
            "sequence_i5": [],
            "name_i7": [],
            "name_i5": [],
        }
        for idx, row in self.df.iterrows():
            seq_i7s = row["sequence_i7"].split(";") if pd.notna(row["sequence_i7"]) else []
            seq_i5s = row["sequence_i5"].split(";") if pd.notna(row["sequence_i5"]) else []

            for i in range(max(len(seq_i7s), len(seq_i5s))):
                barcode_table_data["library_id"].append(row["library_id"])
                barcode_table_data["library_name"].append(row["library_name"])
                barcode_table_data["pool"].append(row["pool"])
                barcode_table_data["sequence_i7"].append(seq_i7s[i] if len(seq_i7s) > i else None)
                barcode_table_data["sequence_i5"].append(seq_i5s[i] if len(seq_i5s) > i else None)
        
        barcode_table = pd.DataFrame(barcode_table_data)

        complete_pool_indexing_form = CompleteLibraryIndexingForm()
        complete_pool_indexing_form.metadata["lab_prep_id"] = self.lab_prep.id
        complete_pool_indexing_form.add_table("library_table", self.df)
        complete_pool_indexing_form.add_table("barcode_table", barcode_table)
        complete_pool_indexing_form.update_data()
        complete_pool_indexing_form.prepare()
        return complete_pool_indexing_form.make_response()