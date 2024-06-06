import os
from typing import Optional, Literal
from uuid import uuid4
from pathlib import Path

import pandas as pd
import numpy as np

from flask_wtf.file import FileField, FileAllowed
from wtforms import SelectField, StringField
from wtforms.validators import Optional as OptionalValidator
from flask import Response
from werkzeug.utils import secure_filename

from limbless_db.categories import LibraryType

from .... import logger, tools
from ....tools import SpreadSheetColumn
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm
from .PoolMappingForm import PoolMappingForm
from .CompleteSASForm import CompleteSASForm


class FRPAnnotationForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-10.html"
    _form_label = "frp_annotation_form"

    columns = {
        "library_name": SpreadSheetColumn("A", "library_name", "Library Name", "text", 170, str),
        "barcode_id": SpreadSheetColumn("B", "barcode_id", "Bardcode ID", "text", 170, str),
        "sample_name": SpreadSheetColumn("C", "sample_name", "Sample Name", "text", 170, str),
    }
    _mapping: dict[str, str] = dict([(col.name, col.label) for col in columns.values()])
    _required_columns: list[str] = [col.name for col in columns.values()]

    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]

    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
        "invalid_input": "#AED6F1"
    }

    separator = SelectField(choices=_allowed_extensions, default="tsv", coerce=str)
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])
    spreadsheet_dummy = StringField(validators=[OptionalValidator()])

    def __init__(self, previous_form: Optional[TableDataForm] = None, formdata: dict = {}, uuid: Optional[str] = None, input_type: Optional[Literal["spreadsheet", "file"]] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid, previous_form=previous_form)
        self.input_type = input_type
        self._context["columns"] = FRPAnnotationForm.columns.values()
        self._context["active_tab"] = "help"
        self._context["colors"] = FRPAnnotationForm.colors
        self.spreadsheet_style = dict()

    def get_template(self) -> pd.DataFrame:
        df = pd.DataFrame(columns=[col.name for col in FRPAnnotationForm.columns.values()])
        return df

    def prepare(self):
        # self._context["spreadsheet_data"] = self.get_template().replace(np.nan, "").values.tolist()
        pass

    def validate(self) -> bool:
        validated = super().validate()
        self.flex_table = None

        if self.input_type is None:
            logger.error("Input type not specified in constructor.")
            raise Exception("Input type not specified in constructor.")
        
        self._context["active_tab"] = self.input_type
        
        if self.input_type == "file":
            if self.file.data is None:
                self.file.errors = ("Upload a file.",)
                return False
            
        if self.input_type == "file":
            filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
            filename = secure_filename(filename)
            filepath = os.path.join("uploads", "seq_request", filename)
            self.file.data.save(filepath)

            sep = "\t" if self.separator.data == "tsv" else ","

            try:
                self.flex_table = pd.read_csv(filepath, sep=sep, index_col=False, header=0)
                validated = True
            except pd.errors.ParserError as e:
                self.file.errors = (str(e),)
                validated = False
            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)

            if not validated or self.flex_table is None:
                return False
            
            missing = []
            for col in FRPAnnotationForm._required_columns:
                if col not in self.flex_table.columns:
                    missing.append(col)
            
                if len(missing) > 0:
                    self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                    return False
                
            self.flex_table = self.flex_table.rename(columns=FRPAnnotationForm._mapping)
            self.flex_table = self.flex_table.replace(r'^\s*$', None, regex=True)
            self.flex_table = self.flex_table.dropna(how="all")

            if len(self.flex_table) == 0:
                self.file.errors = ("File is empty.",)
                return False
            
            if os.path.exists(filepath):
                os.remove(filepath)

        elif self.input_type == "spreadsheet":
            import json
            data = json.loads(self.formdata["spreadsheet"])  # type: ignore
            try:
                self.flex_table = pd.DataFrame(data)
            except ValueError as e:
                self.spreadsheet_dummy.errors = (str(e),)
                return False
            
            columns = list(FRPAnnotationForm.columns.keys())
            if len(self.flex_table.columns) != len(columns):
                self.spreadsheet_dummy.errors = (f"Invalid number of columns (expected {len(columns)}). Do not insert new columns or rearrange existing columns.",)
                return False
            
            self.flex_table.columns = columns
            self.flex_table = self.flex_table.replace(r'^\s*$', None, regex=True)
            self.flex_table = self.flex_table.dropna(how="all")

            if len(self.flex_table) == 0:
                self.spreadsheet_dummy.errors = ("Please fill-out spreadsheet or upload a file.",)
                return False
            
        if self.flex_table is None:
            return False
        
        library_table: pd.DataFrame = self.tables["library_table"]

        self.file.errors = []
        self.spreadsheet_dummy.errors = []

        self.flex_table["library_name"] = self.flex_table["library_name"].apply(lambda x: tools.make_alpha_numeric(x))

        duplicate_samples = self.flex_table.duplicated(subset=["library_name", "sample_name"], keep=False)
        duplicate_barcode = self.flex_table.duplicated(subset=["library_name", "barcode_id"], keep=False)

        for i, (idx, row) in enumerate(self.flex_table.iterrows()):
            if pd.isna(row["library_name"]):
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: Library is missing.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: Library is missing.")
                    self.spreadsheet_style[f"{FRPAnnotationForm.columns['library_name'].column}{i + 1}"] = f"background-color: {FRPAnnotationForm.colors['missing_value']};"
            elif row["library_name"] not in library_table["library_name"].values:
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: Library is not found in the library table.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: Library is not found in the library table.")
                    self.spreadsheet_style[f"{FRPAnnotationForm.columns['library_name'].column}{i + 1}"] = f"background-color: {FRPAnnotationForm.colors['invalid_value']};"
            elif (library_table[library_table["library_name"] == row["library_name"]]["library_type_id"] != LibraryType.TENX_FLEX.id).any():
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: Library is not a Fixed RNA Profiling library.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: Library is not a Fixed RNA Profiling library.")
                    self.spreadsheet_style[f"{FRPAnnotationForm.columns['library_name'].column}{i + 1}"] = f"background-color: {FRPAnnotationForm.colors['invalid_value']};"
            elif duplicate_barcode.at[idx]:
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: 'Barcode ID' is not unique in the library.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: 'Barcode ID' is not unique in the library.")
                    self.spreadsheet_style[f"{FRPAnnotationForm.columns['barcode_id'].column}{i + 1}"] = f"background-color: {FRPAnnotationForm.colors['duplicate_value']};"

            if pd.isna(row["barcode_id"]):
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: 'Barcode ID' is missing.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: 'Barcode ID' is missing.")
                    self.spreadsheet_style[f"{FRPAnnotationForm.columns['barcode_id'].column}{i + 1}"] = f"background-color: {FRPAnnotationForm.colors['missing_value']};"
            
            if pd.isna(row["sample_name"]):
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: 'Sample Name' is missing.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: 'Sample Name' is missing.")
                    self.spreadsheet_style[f"{FRPAnnotationForm.columns['sample_name'].column}{i + 1}"] = f"background-color: {FRPAnnotationForm.colors['missing_value']};"
            elif duplicate_samples.at[idx]:
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: 'Sample Name' is not unique in the library.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: 'Sample Name' is not unique in the library")
                    self.spreadsheet_style[f"{FRPAnnotationForm.columns['sample_name'].column}{i + 1}"] = f"background-color: {FRPAnnotationForm.colors['duplicate_value']};"

        if self.input_type == "file":
            validated = validated and len(self.file.errors) == 0
        elif self.input_type == "spreadsheet":
            validated = validated and (len(self.spreadsheet_dummy.errors) == 0 and len(self.spreadsheet_style) == 0)
        return validated
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            if self.input_type == "spreadsheet":
                self._context["spreadsheet_style"] = self.spreadsheet_style
                if self.flex_table is not None:
                    context["spreadsheet_data"] = self.flex_table.replace(np.nan, "").values.tolist()
                    if context["spreadsheet_data"] == []:
                        context["spreadsheet_data"] = [[]]
            return self.make_response(**context)
        
        if self.flex_table is None:
            logger.error(f"{self.uuid}: FRP table is None.")
            raise Exception("FRP table is None.")
        
        library_table = self.tables["library_table"]
        
        self.flex_table["sample_id"] = None

        for (library_name, sample_id), _ in library_table.groupby(["library_name", "sample_id"]):
            self.flex_table.loc[self.flex_table["library_name"] == library_name, "sample_id"] = sample_id
        
        self.add_table("flex_table", self.flex_table)
        self.update_data()

        if "pool" in library_table.columns:
            pool_mapping_form = PoolMappingForm(self, uuid=self.uuid)
            pool_mapping_form.prepare()
            return pool_mapping_form.make_response(**context)
        
        complete_sas_form = CompleteSASForm(self, uuid=self.uuid)
        complete_sas_form.prepare()
        return complete_sas_form.make_response(**context)



        

        
