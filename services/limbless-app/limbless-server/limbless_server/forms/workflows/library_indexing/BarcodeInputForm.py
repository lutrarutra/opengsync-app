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

from .... import logger, tools
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

    def __init__(self, lab_prep: models.LabPrep, formdata: dict = {}, uuid: Optional[str] = None, input_type: Optional[Literal["spreadsheet", "plate"]] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.input_type = input_type
        self.lab_prep = lab_prep
        self.library_table = self.get_template()
        self._context["columns"] = BarcodeInputForm.columns.values()
        self._context["colors"] = BarcodeInputForm.colors
        self._context["active_tab"] = input_type if input_type else "help"
        self._context["lab_prep"] = lab_prep
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

        if self.input_type is None or self.input_type not in ["spreadsheet", "plate"]:
            logger.error("Input type not set")
            raise ValueError("Input type not set")
            
        # if self.input_type == "plate":
        #     if not self.plate_form.index_kit.selected.data:  # type: ignore
        #         self.plate_form.index_kit.selected.errors = ("Select index kit.",)  # type: ignore
        #         validated = False
            
        #     try:
        #         starting_index = int(self.plate_form.starting_index.data)
        #     except ValueError:
        #         self.plate_form.starting_index.errors = ("Invalid starting index.",)
        #         validated = False

        #     if len(self.lab_prep.plate.sample_links) + starting_index > 96:  # type: ignore
        #         self.plate_form.starting_index.errors = ("Starting index exceeds plate size.",)
        #         validated = False
            
        if not validated:
            return False
            
        if self.input_type == "spreadsheet":
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
        
        # elif self.input_type == "plate":
        #     if self.lab_prep.plate is None:
        #         logger.error("Pool has no plate")
        #         raise ValueError("Pool has no plate")
            
        #     def get_well(i):
        #         return models.Plate.well_identifier(i, num_cols=12, num_rows=8)

        #     if (index_kit := db.get_index_kit(self.plate_form.index_kit.selected.data)) is None:  # type: ignore
        #         logger.error("Invalid index kit from search-select-component")
        #         raise ValueError("Invalid index kit from search-select-component")
            
        #     self.library_table["kit"] = index_kit.name
        #     self.library_table["kit_id"] = index_kit.id

        #     for i in range(self.lab_prep.plate.num_cols * self.lab_prep.plate.num_rows):
        #         if (sample := db.get_plate_sample(plate_id=self.lab_prep.plate_id, well_idx=i)) is None:
        #             continue
        #         elif isinstance(sample, models.Library):
        #             adapter = db.get_adapter_from_index_kit(index_kit_id=index_kit.id, plate_well=get_well(i + self.plate_form.starting_index.data))
        #             self.library_table.loc[self.library_table["library_id"] == sample.id, "sequence_i7"] = adapter.barcode_1.sequence if adapter.barcode_1 is not None else None
        #             self.library_table.loc[self.library_table["library_id"] == sample.id, "sequence_i5"] = adapter.barcode_2.sequence if adapter.barcode_2 is not None else None
        #         else:
        #             logger.error("Sample (not library) cannot be indexed")  # this should never happen
        #             raise ValueError("Sample (not library) cannot be indexed")

        #     return True
            
        self.df["sequence_i7"] = self.df["sequence_i7"].apply(lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with=""))
        self.df["sequence_i5"] = self.df["sequence_i5"].apply(lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with=""))

        self.spreadsheet_dummy.errors = []

        def add_error(row_num: int, column: str, message: str, color: Literal["missing_value", "invalid_value", "duplicate_value", "invalid_input"]):
            if self.input_type == "spreadsheet":
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

        if self.input_type == "spreadsheet":
            validated = validated and (len(self.spreadsheet_dummy.errors) == 0 and len(self.spreadsheet_style) == 0)

        return validated

    def process_request(self) -> Response:
        if not self.validate():
            if self.input_type == "spreadsheet":
                self._context["spreadsheet_style"] = self.spreadsheet_style
                self._context["spreadsheet_data"] = self.df[BarcodeInputForm.columns.keys()].replace(np.nan, "").values.tolist()
                if self._context["spreadsheet_data"] == []:
                    self._context["spreadsheet_data"] = [[None]]
            else:
                self._context["spreadsheet_data"] = self.library_table[BarcodeInputForm.columns.keys()].replace(np.nan, "").values.tolist()

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
        
        complete_pool_indexing_form = CompleteLibraryIndexingForm()
        complete_pool_indexing_form.metadata["lab_prep_id"] = self.lab_prep.id
        complete_pool_indexing_form.add_table("library_table", self.df)
        complete_pool_indexing_form.update_data()
        complete_pool_indexing_form.prepare()
        return complete_pool_indexing_form.make_response()