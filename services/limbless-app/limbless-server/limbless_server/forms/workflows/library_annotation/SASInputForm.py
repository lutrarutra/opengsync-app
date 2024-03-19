import os
from uuid import uuid4
from pathlib import Path
from typing import Optional, Literal, Any

import pandas as pd
import numpy as np

from flask import Response
from wtforms import SelectField, StringField
from wtforms.validators import Optional as OptionalValidator
from flask_wtf.file import FileField, FileAllowed
from werkzeug.utils import secure_filename

from limbless_db.categories import LibraryType, GenomeRef

from ...HTMXFlaskForm import HTMXFlaskForm
from .ProjectMappingForm import ProjectMappingForm

from dataclasses import dataclass


@dataclass
class SpreadSheetColumn:
    column: str
    label: str
    name: str
    type: Literal["text", "numeric", "dropdown"]
    width: float
    source: Optional[Any] = None


columns = {
    "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 120),
    "library_name": SpreadSheetColumn("B", "library_name", "Library Name", "text", 120),
    "genome": SpreadSheetColumn("C", "genome", "Genome", "dropdown", 100, GenomeRef.names()),
    "project": SpreadSheetColumn("D", "project", "Project", "text", 100),
    "library_type": SpreadSheetColumn("E", "library_type", "Library Type", "dropdown", 100, LibraryType.names()),
    "pool": SpreadSheetColumn("F", "pool", "Pool", "text", 100),
    "index_kit": SpreadSheetColumn("G", "index_kit", "Index Kit", "text", 100),
    "adapter": SpreadSheetColumn("H", "adapter", "Adapter", "text", 100),
    "index_1": SpreadSheetColumn("I", "index_1", "Index 1 (i7)", "text", 100),
    "index_2": SpreadSheetColumn("J", "index_2", "Index 2 (i5)", "text", 100),
    "index_3": SpreadSheetColumn("K", "index_3", "Index 3", "text", 80),
    "index_4": SpreadSheetColumn("L", "index_4", "Index 4", "text", 80),
    "seq_depth": SpreadSheetColumn("F", "seq_depth", "Sequencing Depth", "numeric", 150),
}

errors = {
    "missing_value": "background-color: #FAD7A0;",
    "invalid_value": "background-color: #F5B7B1;",
    "duplicate_value": "background-color: #D7BDE2;",
    "ok": "background-color: #82E0AA;"
}


class SASInputForm(HTMXFlaskForm):
    _template_path = "workflows/library_annotation/sas-1.html"
    _form_label = "sas_input_form"

    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    separator = SelectField(choices=_allowed_extensions, default="tsv", coerce=str)
    file = FileField(validators=[OptionalValidator(), FileAllowed([ext for ext, _ in _allowed_extensions])])
    spreadsheet_dummy = StringField(validators=[OptionalValidator()])

    _feature_mapping_premade = {
        "Sample Name": columns["sample_name"],
        "Library Name": columns["library_name"],
        "Genome": columns["genome"],
        "Project": columns["project"],
        "Library Type": columns["library_type"],
        "Pool": columns["pool"],
        "Index Kit": columns["index_kit"],
        "Adapter": columns["adapter"],
        "Index 1 (i7)": columns["index_1"],
        "Index 2 (i5)": columns["index_2"],
        "Index 3": columns["index_3"],
        "Index 4": columns["index_4"],
    }

    _feature_mapping_raw = {
        "Sample Name": columns["sample_name"],
        "Library Name": columns["library_name"],
        "Genome": columns["genome"],
        "Project": columns["project"],
        "Library Type": columns["library_type"],
        "Sequencing Depth": columns["seq_depth"],
    }

    def __init__(self, type: Literal["raw", "pooled"], formdata: Optional[dict] = None):
        super().__init__(formdata=formdata)
        self.upload_path = os.path.join("uploads", "seq_request")
        self.type = type
        self.spreadsheet_style = dict()

        if not os.path.exists(self.upload_path):
            os.makedirs(self.upload_path)

    def validate(self) -> bool:
        validated = super().validate()
        if "spreadsheet" in self.formdata.keys():  # type: ignore
            self.input_type = "spreadsheet"
        elif self.file.data is not None:
            self.input_type = "file"
        else:
            self.file.errors = ("Please upload a file or fill-out spreadsheet.",)
            self.spreadsheet_dummy.errors = ("Please fill-out spreadsheet or upload a file.",)
            return False
        if not validated:
            return False
        
        if self.input_type == "spreadsheet":
            self.df = self.__parse_spreadsheet(self.formdata["spreadsheet"])  # type: ignore
            self.df = self.df.replace(r'^\s*$', None, regex=True)
            self.df = self.df.dropna(how="all")

            if len(self.df) == 0:
                self.spreadsheet_dummy.errors = ("Please fill-out spreadsheet or upload a file.",)
                return False
                    
        if self.input_type == "file":
            col_mapping = SASInputForm._feature_mapping_raw if self.type == "raw" else SASInputForm._feature_mapping_premade
            
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

        library_name_counts = self.df["library_name"].value_counts()
        for i, (_, row) in enumerate(self.df.iterrows()):
            if pd.isna(row["sample_name"]):
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['sample_name'].column}{i+1}"] = errors["missing_value"]
                else:
                    self.file.errors = (f"Row {i+1} is missing a sample name.",)
                
            if pd.isna(row["library_name"]):
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['library_name'].column}{i+1}"] = errors["missing_value"]
                else:
                    self.file.errors = (f"Row {i+1} is missing a library name.",)
            elif library_name_counts[row["library_name"]] > 1:
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['library_name'].column}{i+1}"] = errors["duplicate_value"]
                else:
                    self.file.errors = (f"Library name '{row['library_name']}' is duplicated.",)

            if pd.isna(row["library_type"]):
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['library_type'].column}{i+1}"] = errors["missing_value"]
                else:
                    self.file.errors = (f"Row {i+1} is missing a library type.",)

            if pd.isna(row["genome"]):
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['genome'].column}{i+1}"] = errors["missing_value"]
                else:
                    self.file.errors = (f"Row {i+1} is missing an genome.",)

            if pd.isna(row["project"]):
                if self.input_type == "spreadsheet":
                    self.spreadsheet_style[f"{columns['project'].column}{i+1}"] = errors["missing_value"]
                else:
                    self.file.errors = (f"Row {i+1} is missing a project.",)
            
            if self.type == "raw":
                if pd.isna(row["seq_depth"]):
                    if self.input_type == "spreadsheet":
                        self.spreadsheet_style[f"{columns['seq_depth'].column}{i+1}"] = errors["missing_value"]
                    else:
                        self.file.errors = (f"Row {i+1} is missing a sequencing depth.",)
                else:
                    try:
                        if isinstance(row["seq_depth"], str):
                            row["seq_depth"] = row["seq_depth"].strip().replace(" ", "")

                        row["seq_depth"] = float(row["seq_depth"])
                    except ValueError:
                        if self.input_type == "spreadsheet":
                            self.spreadsheet_style[f"{columns['seq_depth'].column}{i+1}"] = errors["invalid_value"]
                        else:
                            self.file.errors = (f"Row {i+1} has an invalid sequencing depth.",)

            if self.type == "pooled":
                adapter_defined = pd.notna(row["adapter"])
                index_kit_defined = pd.notna(row["index_kit"])

                if pd.isna(row["pool"]):
                    if self.input_type == "spreadsheet":
                        self.spreadsheet_style[f"{columns['pool'].column}{i+1}"] = errors["missing_value"]
                    else:
                        self.file.errors = (f"Row {i+1} is missing a pool.",)
                
                if adapter_defined and not index_kit_defined:
                    self.spreadsheet_style[f"{columns['index_kit'].column}{i+1}"] = errors["missing_value"]
                elif not adapter_defined and index_kit_defined:
                    self.spreadsheet_style[f"{columns['adapter'].column}{i+1}"] = errors["missing_value"]

                elif not adapter_defined and pd.isna(row["index_1"]):
                    if self.input_type == "spreadsheet":
                        self.spreadsheet_style[f"{columns['adapter'].column}{i+1}"] = errors["missing_value"]
                        self.spreadsheet_style[f"{columns['index_kit'].column}{i+1}"] = errors["missing_value"]
                        self.spreadsheet_style[f"{columns['index_1'].column}{i+1}"] = errors["missing_value"]
                        self.spreadsheet_style[f"{columns['index_2'].column}{i+1}"] = errors["missing_value"]
                    else:
                        self.file.errors = (f"Row {i+1} is missing an adapter and index kit or manually specified indices.",)

            if len(self.spreadsheet_style) != 0 or (self.file.errors is not None and len(self.file.errors) != 0):
                return False

        return True
    
    def get_columns(self):
        if self.type == "raw":
            return list(SASInputForm._feature_mapping_raw.values())
        elif self.type == "pooled":
            return list(SASInputForm._feature_mapping_premade.values())
        
        raise ValueError("Invalid type")
    
    def columns_mapping(self):
        return dict([(col.name, col.label) for col in self.get_columns()])
    
    def __parse_spreadsheet(self, raw_json: str) -> pd.DataFrame:
        import json
        return pd.DataFrame(json.loads(raw_json), columns=[col.label for col in self.get_columns()])
    
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

        if not self.validate() or self.df is None:
            context["columns"] = self.get_columns()
            if self.input_type == "spreadsheet":
                context["spreadsheet_style"] = self.spreadsheet_style
                context["spreadsheet_data"] = self.df.replace(np.nan, "").values.tolist()
                if context["spreadsheet_data"] == []:
                    context["spreadsheet_data"] = [[None]]
            
            return self.make_response(**context)
        
        user_id: int = context["user_id"]

        self.__map_library_types()
        self.__map_organisms()

        data: dict[str, pd.DataFrame | dict] = dict(
            metadata=dict(type=self.type),
            library_table=self.df
        )

        project_mapping_form = ProjectMappingForm()
        context = project_mapping_form.prepare(user_id, data) | context
                
        return project_mapping_form.make_response(**context)
        
