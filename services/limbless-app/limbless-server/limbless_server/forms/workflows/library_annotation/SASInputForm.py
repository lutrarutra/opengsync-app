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

from limbless_db import models, DBSession
from limbless_db.categories import LibraryType, GenomeRef

from .... import logger, db
from ....tools import SpreadSheetColumn, tools
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm
from .IndexKitMappingForm import IndexKitMappingForm
from .CMOReferenceInputForm import CMOReferenceInputForm
from .PoolMappingForm import PoolMappingForm
from .CompleteSASForm import CompleteSASForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .GenomeRefMappingForm import GenomeRefMappingForm
from .FRPAnnotationForm import FRPAnnotationForm
from .LibraryMappingForm import LibraryMappingForm

raw_columns = {
    "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 170, str),
    "library_name": SpreadSheetColumn("B", "library_name", "Library Name", "text", 200, str),
    "genome": SpreadSheetColumn("C", "genome", "Genome", "dropdown", 150, str, GenomeRef.names()),
    "library_type": SpreadSheetColumn("D", "library_type", "Library Type", "dropdown", 200, str, LibraryType.names()),
    "seq_depth": SpreadSheetColumn("E", "seq_depth", "Sequencing Depth", "numeric", 150, float),
}

pooled_columns = {
    "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 170, str),
    "library_name": SpreadSheetColumn("B", "library_name", "Library Name", "text", 200, str),
    "genome": SpreadSheetColumn("C", "genome", "Genome", "dropdown", 150, str, GenomeRef.names()),
    "library_type": SpreadSheetColumn("D", "library_type", "Library Type", "dropdown", 200, str, LibraryType.names()),
    "pool": SpreadSheetColumn("E", "pool", "Pool", "text", 100, str),
    "index_kit": SpreadSheetColumn("F", "index_kit", "Index Kit", "text", 150, str),
    "adapter": SpreadSheetColumn("G", "adapter", "Adapter", "text", 100, str),
    "index_1": SpreadSheetColumn("H", "index_1", "Index 1 (i7)", "text", 120, str),
    "index_2": SpreadSheetColumn("I", "index_2", "Index 2 (i5)", "text", 120, str),
    "index_3": SpreadSheetColumn("J", "index_3", "Index 3", "text", 80, str),
    "index_4": SpreadSheetColumn("K", "index_4", "Index 4", "text", 80, str),
}


class SASInputForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-2.1.html"
    _form_label = "sas_input_form"

    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
    }
    separator = SelectField(choices=_allowed_extensions, default="tsv", coerce=str)
    file = FileField(validators=[OptionalValidator(), FileAllowed([ext for ext, _ in _allowed_extensions])])
    spreadsheet_dummy = StringField(validators=[OptionalValidator()])

    _feature_mapping_raw = dict([(col.name, col) for col in raw_columns.values()])
    _feature_mapping_pooled = dict([(col.name, col) for col in pooled_columns.values()])

    def __init__(self, seq_request: models.SeqRequest, formdata: dict = {}, input_method: Optional[Literal["spreadsheet", "file"]] = None, uuid: Optional[str] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        if uuid is None:
            uuid = formdata.get("file_uuid")
        TableDataForm.__init__(self, uuid=uuid, dirname="library_annotation")

        self.upload_path = os.path.join("uploads", "seq_request")
        self.spreadsheet_style = dict()
        self.input_method = input_method
        self.seq_request = seq_request
        self._context["colors"] = SASInputForm.colors
        self._context["active_tab"] = "help"
        self._context["seq_request"] = seq_request

        if not os.path.exists(self.upload_path):
            os.makedirs(self.upload_path)

    def validate(self) -> bool:
        validated = super().validate()

        if self.metadata["workflow_type"] == "raw":
            columns = raw_columns
        elif self.metadata["workflow_type"] == "pooled":
            columns = pooled_columns
        else:
            logger.error("Invalid type.")
            raise ValueError("Invalid type.")

        if self.input_method is None:
            logger.error("Input type not specified in constructor.")
            raise Exception("Input type not specified in constructor.")
        
        self._context["active_tab"] = self.input_method

        if self.input_method == "file":
            if self.file.data is None:
                self.file.errors = ("Upload a file.",)
                return False
        
        if not validated:
            return False
                
        if self.input_method == "spreadsheet":
            import json
            data = json.loads(self.formdata["spreadsheet"])  # type: ignore
            try:
                self.df = pd.DataFrame(data)
            except ValueError as e:
                self.spreadsheet_dummy.errors = (str(e),)
                return False
            
            if len(self.df.columns) != len(list(columns.keys())):
                self.spreadsheet_dummy.errors = (f"Invalid number of columns (expected {len(columns)}). Do not insert new columns or rearrange existing columns.",)
                return False
            
            self.df.columns = list(columns.keys())
            self.df = self.df.replace(r'^\s*$', None, regex=True)
            self.df = self.df.dropna(how="all")

            if len(self.df) == 0:
                self.spreadsheet_dummy.errors = ("Please fill-out spreadsheet or upload a file.",)
                return False

        elif self.input_method == "file":
            col_mapping = SASInputForm._feature_mapping_raw if self.metadata["workflow_type"] == "raw" else SASInputForm._feature_mapping_pooled
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
            if self.input_method == "spreadsheet":
                self.spreadsheet_dummy.errors = ("Please fill-out spreadsheet.",)
            elif self.input_method == "file":
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
        seq_request_library_names = [library.name for library in self.seq_request.libraries]

        self.file.errors = []
        self.spreadsheet_dummy.errors = []

        def add_error(row_num: int, column: str, message: str, color: Literal["missing_value", "invalid_value", "duplicate_value"]):
            if self.input_method == "spreadsheet":
                self.spreadsheet_style[f"{columns[column].column}{row_num}"] = f"background-color: {SASInputForm.colors[color]};"
                self.spreadsheet_dummy.errors.append(f"Row {row_num}: {message}")  # type: ignore
            else:
                self.file.errors.append(f"Row {row_num}: {message}")  # type: ignore

        with DBSession(db) as session:
            if (project_id := self.metadata.get("project_id")) is not None:
                if (project := session.get_project(project_id)) is None:
                    logger.error(f"{self.uuid}: Project with ID {project_id} does not exist.")
                    raise ValueError(f"Project with ID {project_id} does not exist.")
            else:
                project = None

            for i, (_, row) in enumerate(self.df.iterrows()):
                if pd.isna(row["sample_name"]):
                    add_error(i + 1, "sample_name", "missing 'Sample Name'", "missing_value")
                elif project is not None and row["sample_name"] in [sample.name for sample in project.samples]:
                    add_error(i + 1, "sample_name", "Sample name already exists in the project. Rename sample or change project", "duplicate_value")
                    
                if pd.isna(row["library_name"]):
                    add_error(i + 1, "library_name", "missing 'Library Name'", "missing_value")

                elif library_name_counts[row["library_name"]] > 1:
                    add_error(i + 1, "library_name", "duplicate 'Library Name'", "duplicate_value")

                elif row["library_name"] in seq_request_library_names:
                    add_error(i + 1, "library_name", "Library name already exists in the request.", "duplicate_value")

                if pd.isna(row["library_type"]):
                    add_error(i + 1, "library_type", "missing 'Library Type'", "missing_value")

                if pd.isna(row["genome"]):
                    add_error(i + 1, "genome", "missing 'Genome'", "missing_value")
                
                if self.metadata["workflow_type"] == "raw":
                    if pd.notna(row["seq_depth"]):
                        try:
                            if isinstance(row["seq_depth"], str):
                                row["seq_depth"] = row["seq_depth"].strip().replace(" ", "")

                            row["seq_depth"] = float(row["seq_depth"])
                        except ValueError:
                            add_error(i + 1, "seq_depth", "invalid 'Sequencing Depth'", "invalid_value")

                elif self.metadata["workflow_type"] == "pooled":
                    adapter_defined = pd.notna(row["adapter"])
                    index_kit_defined = pd.notna(row["index_kit"])

                    if pd.isna(row["pool"]):
                        add_error(i + 1, "pool", "missing 'Pool'", "missing_value")
                    
                    if adapter_defined and not index_kit_defined:
                        add_error(i + 1, "index_kit", "missing 'Index Kit'", "missing_value")
                    elif not adapter_defined and index_kit_defined:
                        add_error(i + 1, "adapter", "missing 'Adapter'", "missing_value")

                    elif not adapter_defined and pd.isna(row["index_1"]):
                        add_error(i + 1, "index_1", "missing 'Index 1'", "missing_value")
                        add_error(i + 1, "adapter", "missing 'Adapter'", "missing_value")
                        add_error(i + 1, "index_kit", "missing 'Index Kit'", "missing_value")

        if len(self.spreadsheet_style) != 0 or (self.file.errors is not None and len(self.file.errors) != 0):
            return False
            
        self.df = self.df[[col.label for col in self.get_columns()]]
        return True
    
    def get_columns(self):
        if self.metadata["workflow_type"] == "raw":
            return list(SASInputForm._feature_mapping_raw.values())
        elif self.metadata["workflow_type"] == "pooled":
            return list(SASInputForm._feature_mapping_pooled.values())
        raise ValueError("Invalid type")
    
    def columns_mapping(self):
        return dict([(col.name, col.label) for col in self.get_columns()])
    
    def __map_library_types(self):
        library_type_map = {}
        for id, e in LibraryType.as_tuples():
            library_type_map[e.display_name] = id
        
        self.df["library_type_id"] = self.df["library_type"].map(library_type_map)

    def __map_organisms(self):
        organism_map = {}
        for id, e in GenomeRef.as_tuples():
            organism_map[e.display_name] = id
        
        self.df["genome_id"] = self.df["genome"].map(organism_map)
    
    def process_request(self) -> Response:
        if not self.validate() or self.df is None:
            if self.input_method == "spreadsheet":
                self._context["spreadsheet_style"] = self.spreadsheet_style
                self._context["spreadsheet_data"] = self.df.replace(np.nan, "").values.tolist()
                if self._context["spreadsheet_data"] == []:
                    self._context["spreadsheet_data"] = [[None]]
            
            return self.make_response()

        self.__map_library_types()
        self.__map_organisms()
        self.add_table("library_table", self.df)
        self.update_data()

        if self.df["genome_id"].isna().any():
            organism_mapping_form = GenomeRefMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            organism_mapping_form.prepare()
            return organism_mapping_form.make_response()
        
        if self.df["library_type_id"].isna().any():
            library_mapping_form = LibraryMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            library_mapping_form.prepare()
            return library_mapping_form.make_response()

        if "index_kit" in self.df and not self.df["index_kit"].isna().all():
            index_kit_mapping_form = IndexKitMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            index_kit_mapping_form.prepare()
            return index_kit_mapping_form.make_response()
        
        if self.df["library_type_id"].isin([
            LibraryType.MULTIPLEXING_CAPTURE.id,
        ]).any():
            cmo_reference_input_form = CMOReferenceInputForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return cmo_reference_input_form.make_response()
        
        if (self.df["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id).any():
            visium_annotation_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            visium_annotation_form.prepare()
            return visium_annotation_form.make_response()
        
        if LibraryType.TENX_FLEX.id in self.df["library_type_id"].values and "pool" in self.df.columns:
            frp_annotation_form = FRPAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            frp_annotation_form.prepare()
            return frp_annotation_form.make_response()
        
        if "pool" in self.df.columns:
            pool_mapping_form = PoolMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            pool_mapping_form.prepare()
            return pool_mapping_form.make_response()
    
        complete_sas_form = CompleteSASForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        complete_sas_form.prepare()
        return complete_sas_form.make_response()
