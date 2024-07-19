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

from .... import logger, db
from ....tools import SpreadSheetColumn, tools
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm
from .CMOReferenceInputForm import CMOReferenceInputForm
from .CompleteSASForm import CompleteSASForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .GenomeRefMappingForm import GenomeRefMappingForm
from .FRPAnnotationForm import FRPAnnotationForm
from .LibraryMappingForm import LibraryMappingForm

raw_columns = {
    "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 200, str),
    "genome": SpreadSheetColumn("B", "genome", "Genome", "dropdown", 200, str, GenomeRef.names()),
    "library_type": SpreadSheetColumn("C", "library_type", "Library Type", "dropdown", 200, str, LibraryType.names()),
    "seq_depth": SpreadSheetColumn("D", "seq_depth", "Sequencing Depth", "numeric", 150, float),
}

pooled_columns = {
    "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 200, str),
    "genome": SpreadSheetColumn("B", "genome", "Genome", "dropdown", 200, str, GenomeRef.names()),
    "library_type": SpreadSheetColumn("C", "library_type", "Library Type", "dropdown", 200, str, LibraryType.names()),
    "index_i7": SpreadSheetColumn("D", "index_i7", "Index i7 sequence/name", "text", 250, str),
    "index_i5": SpreadSheetColumn("E", "index_i5", "Index i5 sequence/name", "text", 250, str),
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

        self.file.errors = []
        self.spreadsheet_dummy.errors = []

        def add_error(row_num: int, column: str, message: str, color: Literal["missing_value", "invalid_value", "duplicate_value"]):
            if self.input_method == "spreadsheet":
                self.spreadsheet_style[f"{columns[column].column}{row_num}"] = f"background-color: {SASInputForm.colors[color]};"
                self.spreadsheet_dummy.errors.append(f"Row {row_num}: {message}")  # type: ignore
            else:
                self.file.errors.append(f"Row {row_num}: {message}")  # type: ignore

        self.library_table = self.df.copy()
        if self.metadata["workflow_type"] == "pooled":
            self.library_table["index_i7_sequences"] = None
            self.library_table["index_i5_sequences"] = None
            self.library_table["index_i7_name"] = None
            self.library_table["index_i5_name"] = None

        def base_filter(x: str) -> list[str]:
            return [c for c in x if c not in "ACGT"]
        
        duplicate_sample_libraries = self.library_table.duplicated(subset=["sample_name", "library_type"], keep=False)

        seq_request_samples = db.get_seq_request_samples_df(self.seq_request.id)

        for i, (idx, row) in enumerate(self.df.iterrows()):
            if pd.isna(row["sample_name"]):
                add_error(i + 1, "sample_name", "missing 'Sample Name'", "missing_value")

            if duplicate_sample_libraries[i]:
                add_error(i + 1, "sample_name", "Duplicate 'Sample Name' and 'Library Type'", "duplicate_value")

            if ((seq_request_samples["sample_name"] == row["sample_name"]) & (seq_request_samples["library_type"].apply(lambda x: x.name) == row["library_type"])).any():
                add_error(i + 1, "library_type", f"You already have '{row['library_type']}'-library from sample {row['sample_name']} in the request", "duplicate_value")

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
                if pd.isna(row["index_i7"]):
                    add_error(i + 1, "index_i7", "missing 'Index i7'", "missing_value")
                    continue

                if (index_1_kit_id := self.metadata["index_1_kit_id"]) is not None:
                    if (index_1_kit := db.get_index_kit(index_1_kit_id)) is None:
                        logger.error(f"{self.uuid}: Index kit with ID {index_1_kit_id} does not exist.")
                        raise ValueError(f"Index kit with ID {index_1_kit_id} does not exist.")
                    if pd.isna(row["index_i7"]):
                        add_error(i + 1, "index_i7", "missing 'Index i7'", "missing_value")
                        continue
                    
                    if (adapter_1 := db.get_adapter_from_index_kit(index_kit_id=index_1_kit_id, adapter=row["index_i7"].strip())) is None:
                        add_error(i + 1, "index_i7", f"Adapter '{row['index_i7']}' not found in selected index-kit '{index_1_kit.name}'", "invalid_value")
                        continue
                    
                    if (index_2_kit_id := self.metadata["index_2_kit_id"]) is None or index_1_kit_id == self.metadata["index_2_kit_id"]:
                        adapter_2 = adapter_1
                        index_2_kit = index_1_kit
                    else:
                        if (index_2_kit := db.get_index_kit(index_2_kit_id)) is None:
                            logger.error(f"{self.uuid}: Index kit with ID {index_2_kit_id} does not exist.")
                            raise ValueError(f"Index kit with ID {index_2_kit_id} does not exist.")
                        
                        if (adapter_2 := db.get_adapter_from_index_kit(index_kit_id=index_2_kit_id, adapter=row["index_i5"].strip())) is None:
                            add_error(i + 1, "index_i5", f"Adapter '{row['index_i5']}' not found in selected index-kit '{index_2_kit.name}'", "invalid_value")
                            continue

                    self.library_table.at[idx, "index_i7_sequences"] = ";".join([bc_i7.sequence for bc_i7 in adapter_1.barcodes_i7])
                    self.library_table.at[idx, "index_i7_name"] = adapter_1.name
                    self.library_table.at[idx, "index_i5_sequences"] = ";".join([bc_i5.sequence for bc_i5 in adapter_2.barcodes_i5])
                    if len(adapter_2.barcodes_i5) > 0:
                        self.library_table.at[idx, "index_i5_name"] = adapter_2.name

                else:
                    index_i7_sequences = row["index_i7"].split(";")
                    
                    for index_i7_sequence in index_i7_sequences:
                        if len(unknown_bases := base_filter(index_i7_sequence)) > 0:
                            add_error(i + 1, "index_i7", f"Invalid base(s) in 'Index i7': {', '.join(unknown_bases)}", "invalid_value")

                    self.library_table.at[idx, "index_i7_sequences"] = ";".join(index_i7_sequences)
                    
                    if pd.notna(row["index_i5"]):
                        index_i5_sequences = row["index_i5"].split(";")
                        if len(index_i5_sequences) != len(index_i7_sequences):
                            add_error(i + 1, "index_i5", "Number of 'Index i5'-barcodes sequences should match 'Index i7'-barcodes", "invalid_value")
                        for index_i5_sequence in index_i5_sequences:
                            if len(unknown_bases := base_filter(index_i5_sequence)) > 0:
                                add_error(i + 1, "index_i5", f"Invalid base(s) in 'Index i5': {', '.join(unknown_bases)}", "invalid_value")

                        self.library_table.at[idx, "index_i5_sequences"] = ";".join(index_i5_sequences)

        if len(self.spreadsheet_style) != 0 or (self.file.errors is not None and len(self.file.errors) != 0):
            return False
            
        self.df = self.library_table.drop(columns=["index_i7", "index_i5"], errors="ignore")
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
        self.df["library_name"] = self.df["sample_name"] + self.df["library_type_id"].apply(lambda x: f"_{LibraryType.get(x).assay_type}")

    def __map_genome_ref(self):
        organism_map = {}
        for id, e in GenomeRef.as_tuples():
            organism_map[e.display_name] = id
        
        self.df["genome_id"] = self.df["genome"].map(organism_map)

    def __map_existing_samples(self):
        self.df["sample_id"] = None
        if self.metadata["project_id"] is None:
            return
        if (project := db.get_project(self.metadata["project_id"])) is None:
            logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
            raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
        
        for sample in project.samples:
            self.df.loc[self.df["sample_name"] == sample.name, "sample_id"] = sample.id
    
    def process_request(self) -> Response:
        if not self.validate() or self.df is None:
            if self.input_method == "spreadsheet":
                self._context["spreadsheet_style"] = self.spreadsheet_style
                self._context["spreadsheet_data"] = self.df.replace(np.nan, "").values.tolist()
                if self._context["spreadsheet_data"] == []:
                    self._context["spreadsheet_data"] = [[None]]
            
            return self.make_response()

        self.__map_library_types()
        self.__map_genome_ref()
        self.__map_existing_samples()
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
    
        complete_sas_form = CompleteSASForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        complete_sas_form.prepare()
        return complete_sas_form.make_response()
