import os
from uuid import uuid4
from pathlib import Path
from typing import Optional, Literal

import pandas as pd
import numpy as np

from flask import Response
from wtforms import SelectField, StringField
from wtforms.validators import Optional as OptionalValidator
from flask_wtf.file import FileField, FileAllowed
from werkzeug.utils import secure_filename

from limbless_db import models
from limbless_db.categories import LibraryType, GenomeRef

from .... import logger
from ....tools import SpreadSheetColumn, tools
from ...HTMXFlaskForm import HTMXFlaskForm
from .ProjectMappingForm import ProjectMappingForm

raw_columns = {
    "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 170, str),
    "library_name": SpreadSheetColumn("B", "library_name", "Library Name", "text", 200, str),
    "genome": SpreadSheetColumn("C", "genome", "Genome", "dropdown", 150, str, GenomeRef.names()),
    "project": SpreadSheetColumn("D", "project", "Project", "text", 150, str),
    "library_type": SpreadSheetColumn("E", "library_type", "Library Type", "dropdown", 150, str, LibraryType.names()),
    "seq_depth": SpreadSheetColumn("F", "seq_depth", "Sequencing Depth", "numeric", 150, float),
}

pooled_columns = {
    "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 170, str),
    "library_name": SpreadSheetColumn("B", "library_name", "Library Name", "text", 200, str),
    "genome": SpreadSheetColumn("C", "genome", "Genome", "dropdown", 150, str, GenomeRef.names()),
    "project": SpreadSheetColumn("D", "project", "Project", "text", 150, str),
    "library_type": SpreadSheetColumn("E", "library_type", "Library Type", "dropdown", 100, str, LibraryType.names()),
    "pool": SpreadSheetColumn("F", "pool", "Pool", "text", 100, str),
    "index_kit": SpreadSheetColumn("G", "index_kit", "Index Kit", "text", 150, str),
    "adapter": SpreadSheetColumn("H", "adapter", "Adapter", "text", 100, str),
    "index_1": SpreadSheetColumn("I", "index_1", "Index 1 (i7)", "text", 120, str),
    "index_2": SpreadSheetColumn("J", "index_2", "Index 2 (i5)", "text", 120, str),
    "index_3": SpreadSheetColumn("K", "index_3", "Index 3", "text", 80, str),
    "index_4": SpreadSheetColumn("L", "index_4", "Index 4", "text", 80, str),
}


class SASInputForm(HTMXFlaskForm):
    _template_path = "workflows/library_annotation/sas-1.html"
    _form_label = "sas_input_form"

    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
        "ok": "#82E0AA"
    }
    separator = SelectField(choices=_allowed_extensions, default="tsv", coerce=str)
    file = FileField(validators=[OptionalValidator(), FileAllowed([ext for ext, _ in _allowed_extensions])])
    spreadsheet_dummy = StringField(validators=[OptionalValidator()])

    _feature_mapping_raw = dict([(col.name, col) for col in raw_columns.values()])
    _feature_mapping_pooled = dict([(col.name, col) for col in pooled_columns.values()])

    def __init__(self, type: Literal["raw", "pooled"], formdata: Optional[dict] = None, input_type: Optional[Literal["spreadsheet", "file"]] = None):
        super().__init__(formdata=formdata)
        self.upload_path = os.path.join("uploads", "seq_request")
        self.type = type
        self.spreadsheet_style = dict()
        self._context["columns"] = self.get_columns()
        self._context["colors"] = SASInputForm.colors
        self._context["active_tab"] = "help"
        self.input_type = input_type

        if not os.path.exists(self.upload_path):
            os.makedirs(self.upload_path)

    def validate(self, seq_request: models.SeqRequest) -> bool:
        validated = super().validate()

        if self.type == "raw":
            columns = raw_columns
        elif self.type == "pooled":
            columns = pooled_columns
        else:
            logger.error("Invalid type.")
            raise ValueError("Invalid type.")

        if self.input_type is None:
            logger.error("Input type not specified in constructor.")
            raise Exception("Input type not specified in constructor.")
        
        self._context["active_tab"] = self.input_type

        if self.input_type == "file":
            if self.file.data is None:
                self.file.errors = ("Upload a file.",)
                return False
        
        if not validated:
            return False
                
        if self.input_type == "spreadsheet":
            import json
            data = json.loads(self.formdata["spreadsheet"])  # type: ignore
            self.df = pd.DataFrame(data, columns=[col.label for col in self.get_columns()])

        elif self.input_type == "file":
            col_mapping = SASInputForm._feature_mapping_raw if self.type == "raw" else SASInputForm._feature_mapping_pooled
            sep = "\t" if self.separator.data == "tsv" else ","
            filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
            filename = secure_filename(filename)
            filepath = os.path.join(self.upload_path, filename)
            self.file.data.save(filepath)
            
            try:
                self.df = pd.read_csv(filepath, sep=sep, index_col=False, header=0)
            except pd.errors.ParserError as e:
                self.file.errors = (str(e),)
                if os.path.exists(filepath):
                    os.remove(filepath)
                return False

            if os.path.exists(filepath):
                os.remove(filepath)

            missing_cols = [col for col in col_mapping.keys() if col not in self.df.columns]
            if len(missing_cols) > 0:
                self.file.errors = (str(f"Uploaded table is missing column(s): [{', '.join(missing_cols)}]"),)
                return False

            self.df = self.df.rename(columns=self.columns_mapping())

        self.df = self.df.replace(r'^\s*$', None, regex=True)
        self.df = self.df.dropna(how="all")
        if len(self.df) == 0:
            if self.input_type == "spreadsheet":
                self.spreadsheet_dummy.errors = ("Please fill-out spreadsheet.",)
            elif self.input_type == "file":
                self.file.errors = ("File is empty.",)
            return False

        for label, column in columns.items():
            if column.var_type == str and column.source is None:
                self.df[label] = self.df[label].apply(tools.make_alpha_numeric)
            elif column.var_type == float:
                self.df[label] = self.df[label].apply(tools.parse_float)
            elif column.var_type == int:
                self.df[label] = self.df[label].apply(tools.parse_int)

        library_name_counts = self.df["library_name"].value_counts()
        seq_request_library_names = [library.name for library in seq_request.libraries]

        for i, (_, row) in enumerate(self.df.iterrows()):
            if pd.isna(row["sample_name"]):
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['sample_name'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"
                else:
                    self.file.errors = (f"Row {i+1} is missing a sample name.",)
                
            if pd.isna(row["library_name"]):
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['library_name'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"
                else:
                    self.file.errors = (f"Row {i+1} is missing a library name.",)
            elif library_name_counts[row["library_name"]] > 1:
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['library_name'].column}{i+1}"] = f"background-color: {SASInputForm.colors['duplicate_value']};"
                else:
                    self.file.errors = (f"Library name '{row['library_name']}' is duplicated.",)
            elif row["library_name"] in seq_request_library_names:
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['library_name'].column}{i+1}"] = f"background-color: {SASInputForm.colors['duplicate_value']};"
                else:
                    self.file.errors = (f"Library name '{row['library_name']}' already exists in the request.",)

            if pd.isna(row["library_type"]):
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['library_type'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"
                else:
                    self.file.errors = (f"Row {i+1} is missing a library type.",)

            if pd.isna(row["genome"]):
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['genome'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"
                else:
                    self.file.errors = (f"Row {i+1} is missing an genome.",)

            if pd.isna(row["project"]):
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['project'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"
                else:
                    self.file.errors = (f"Row {i+1} is missing a project.",)
            
            if self.type == "raw":
                if pd.isna(row["seq_depth"]):
                    if self.input_type == "spreadsheet":
                        self.spreadsheet_style[f"{columns['seq_depth'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"
                    else:
                        self.file.errors = (f"Row {i+1} is missing a sequencing depth.",)
                else:
                    try:
                        if isinstance(row["seq_depth"], str):
                            row["seq_depth"] = row["seq_depth"].strip().replace(" ", "")

                        row["seq_depth"] = float(row["seq_depth"])
                    except ValueError:
                        if self.input_type == "spreadsheet":
                            self.spreadsheet_style[f"{columns['seq_depth'].column}{i+1}"] = f"background-color: {SASInputForm.colors['invalid_value']};"
                        else:
                            self.file.errors = (f"Row {i+1} has an invalid sequencing depth.",)

            elif self.type == "pooled":
                adapter_defined = pd.notna(row["adapter"])
                index_kit_defined = pd.notna(row["index_kit"])

                if pd.isna(row["pool"]):
                    if self.input_type == "spreadsheet":
                        self.spreadsheet_style[f"{columns['pool'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"
                    else:
                        self.file.errors = (f"Row {i+1} is missing a pool.",)
                
                if adapter_defined and not index_kit_defined:
                    self.spreadsheet_style[f"{columns['index_kit'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"
                elif not adapter_defined and index_kit_defined:
                    self.spreadsheet_style[f"{columns['adapter'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"

                elif not adapter_defined and pd.isna(row["index_1"]):
                    if self.input_type == "spreadsheet":
                        self.spreadsheet_style[f"{columns['adapter'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"
                        self.spreadsheet_style[f"{columns['index_kit'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"
                        self.spreadsheet_style[f"{columns['index_1'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"
                        self.spreadsheet_style[f"{columns['index_2'].column}{i+1}"] = f"background-color: {SASInputForm.colors['missing_value']};"
                    else:
                        self.file.errors = (f"Row {i+1} is missing an adapter and index kit or manually specified indices.",)

        if len(self.spreadsheet_style) != 0 or (self.file.errors is not None and len(self.file.errors) != 0):
            return False
            
        self.df = self.df[[col.label for col in self.get_columns()]]
        return True
    
    def get_columns(self):
        if self.type == "raw":
            return list(SASInputForm._feature_mapping_raw.values())
        elif self.type == "pooled":
        
            return list(SASInputForm._feature_mapping_pooled.values())
        raise ValueError("Invalid type")
    
    def columns_mapping(self):
        return dict([(col.name, col.label) for col in self.get_columns()])
    
    def __map_library_types(self):
        library_type_map = {}
        for id, e in LibraryType.as_tuples():
            library_type_map[e.name] = id
        
        self.df["library_type_id"] = self.df["library_type"].map(library_type_map)
        self.df["is_cmo_sample"] = False
        for sample_name, _df in self.df.groupby("sample_name"):
            if LibraryType.MULTIPLEXING_CAPTURE.id in _df["library_type_id"].unique():
                self.df.loc[self.df["sample_name"] == sample_name, "is_cmo_sample"] = True

    def __map_organisms(self):
        organism_map = {}
        for id, e in GenomeRef.as_tuples():
            organism_map[e.name] = id
        
        self.df["genome_id"] = self.df["genome"].map(organism_map)
    
    def process_request(self, **context) -> Response:
        context["type"] = self.type
        user_id: int = context["user_id"]
        seq_request: models.SeqRequest = context["seq_request"]

        if not self.validate(seq_request) or self.df is None:
            if self.input_type == "spreadsheet":
                context["spreadsheet_style"] = self.spreadsheet_style
                context["spreadsheet_data"] = self.df.replace(np.nan, "").values.tolist()
                if context["spreadsheet_data"] == []:
                    context["spreadsheet_data"] = [[None]]
            
            return self.make_response(**context)

        self.__map_library_types()
        self.__map_organisms()

        data: dict[str, pd.DataFrame | dict] = dict(
            metadata=dict(type=self.type),
            library_table=self.df
        )

        project_mapping_form = ProjectMappingForm()
        project_mapping_form.update_data(data)
        project_mapping_form.prepare(user_id, data)
        return project_mapping_form.make_response(**context)
        
