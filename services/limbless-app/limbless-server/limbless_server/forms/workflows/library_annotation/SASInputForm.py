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
from limbless_db.categories import LibraryType, GenomeRef, BarcodeType, IndexType

from .... import logger, db
from ....tools import SpreadSheetColumn, tools
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm
from .CMOReferenceInputForm import CMOReferenceInputForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .GenomeRefMappingForm import GenomeRefMappingForm
from .FRPAnnotationForm import FRPAnnotationForm
from .LibraryMappingForm import LibraryMappingForm
from .SampleAnnotationForm import SampleAnnotationForm


raw_columns = {
    "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
    "genome": SpreadSheetColumn("B", "genome", "Genome", "dropdown", 200, str, GenomeRef.names()),
    "library_type": SpreadSheetColumn("C", "library_type", "Library Type", "dropdown", 200, str, LibraryType.names()),
    "seq_depth": SpreadSheetColumn("D", "seq_depth", "Sequencing Depth", "numeric", 150, float, clean_up_fnc=lambda x: tools.parse_float(x)),
}

pooled_columns = {
    "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
    "genome": SpreadSheetColumn("B", "genome", "Genome", "dropdown", 200, str, GenomeRef.names()),
    "library_type": SpreadSheetColumn("C", "library_type", "Library Type", "dropdown", 200, str, LibraryType.names()),
    "index_well": SpreadSheetColumn("D", "index_well", "Index Well", "text", 150, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
    "index_i7": SpreadSheetColumn("E", "index_i7", "Index i7 Name", "text", 250, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
    "index_i5": SpreadSheetColumn("F", "index_i5", "Index i5 Name", "text", 250, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
}

manual_index_pooled_columns = {
    "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
    "genome": SpreadSheetColumn("B", "genome", "Genome", "dropdown", 200, str, GenomeRef.names()),
    "library_type": SpreadSheetColumn("C", "library_type", "Library Type", "dropdown", 200, str, LibraryType.names()),
    "index_i7": SpreadSheetColumn("D", "index_i7", "Index i7 Sequence", "text", 250, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
    "index_i5": SpreadSheetColumn("E", "index_i5", "Index i5 Sequence", "text", 250, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
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
    _feature_mapping_pooled_manual_index = dict([(col.name, col) for col in manual_index_pooled_columns.values()])

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

    def prepare(self):
        self._context["index_1_kit_id"] = self.metadata["index_1_kit_id"]
        self._context["index_2_kit_id"] = self.metadata["index_2_kit_id"]

    def validate(self) -> bool:
        validated = super().validate()

        if self.metadata["workflow_type"] == "raw":
            columns = raw_columns
        elif self.metadata["workflow_type"] == "pooled":
            if self.metadata["index_1_kit_id"] is None:
                manual_specified_indices = True
                columns = manual_index_pooled_columns
            else:
                manual_specified_indices = False
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

            kit_1_df = None
            kit_2_df = None
            kit_1 = None
            kit_2 = None
                
            if self.metadata["index_1_kit_id"] is not None:
                if (kit_1 := db.get_index_kit(self.metadata["index_1_kit_id"])) is None:
                    logger.error(f"{self.uuid}: Index kit with ID {self.metadata['index_1_kit_id']} does not exist.")
                    raise ValueError(f"Index kit with ID {self.metadata['index_1_kit_id']} does not exist.")
                
                if len(kit_1_df := db.get_index_kit_barcodes_df(self.metadata["index_1_kit_id"], per_adapter=False)) == 0:
                    logger.error(f"{self.uuid}: Index kit with ID {self.metadata['index_1_kit_id']} does not exist.")
                    raise ValueError(f"Index kit with ID {self.metadata['index_1_kit_id']} does not exist.")
            if self.metadata["index_2_kit_id"] is None or self.metadata["index_2_kit_id"] == self.metadata["index_1_kit_id"]:
                kit_2_df = kit_1_df
                kit_2 = kit_1
            else:
                if (kit_2 := db.get_index_kit(self.metadata["index_2_kit_id"])) is None:
                    logger.error(f"{self.uuid}: Index kit with ID {self.metadata['index_2_kit_id']} does not exist.")
                    raise ValueError(f"Index kit with ID {self.metadata['index_2_kit_id']} does not exist.")
                if len(kit_2_df := db.get_index_kit_barcodes_df(self.metadata["index_2_kit_id"], per_adapter=False)) == 0:
                    logger.error(f"{self.uuid}: Index kit with ID {self.metadata['index_2_kit_id']} does not exist.")
                    raise ValueError(f"Index kit with ID {self.metadata['index_2_kit_id']} does not exist.")
                
        for label, column in columns.items():
            if column.clean_up_fnc is not None:
                self.df[label] = self.df[label].apply(column.clean_up_fnc)

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
                if pd.notna(row["index_i7"]) and pd.notna(row["index_well"]):
                    add_error(i + 1, "index_i7", "You must specify 'Index Well' or 'Index Name', not both", "invalid_value")
                    add_error(i + 1, "index_well", "You must specify 'Index Well' or 'Index Name', not both", "invalid_value")
                    continue
                
                if pd.notna(row["index_well"]) and pd.notna(row["index_i5"]):
                    add_error(i + 1, "index_i5", "You must specify 'Index Well' or 'Index Name', not both", "invalid_value")
                    add_error(i + 1, "index_well", "You must specify 'Index Well' or 'Index Name', not both", "invalid_value")
                    continue
            
                if pd.isna(row["index_i7"]) and pd.isna(row["index_well"]):
                    add_error(i + 1, "index_i7", "You must specify 'Index Well' or 'Index Name'", "missing_value")
                    add_error(i + 1, "index_well", "You must specify 'Index Well' or 'Index Name'", "missing_value")
                    continue

                if not manual_specified_indices:
                    assert kit_1_df is not None and kit_2_df is not None
                    assert kit_1 is not None and kit_2 is not None

                    if pd.isna(row["index_i7"]):
                        if len(index_i7_sequences := kit_1_df.loc[(kit_1_df["well"] == row["index_well"]) & (kit_1_df["type"] == BarcodeType.INDEX_I7), "sequence"].tolist()) == 0:  # type: ignore
                            add_error(i + 1, "index_well", f"Well '{row['index_well']}' not found in specified index-kit for i7.", "invalid_value")
                            continue
                        
                        self.library_table.at[idx, "index_i7_sequences"] = ";".join(index_i7_sequences)
                        self.library_table.at[idx, "index_i7_name"] = row["index_well"]
                        
                        if kit_2.type == IndexType.DUAL_INDEX:
                            if len(index_i5_sequences := kit_2_df.loc[(kit_2_df["well"] == row["index_well"]) & (kit_2_df["type"] == BarcodeType.INDEX_I5), "sequence"].tolist()) == 0:  # type: ignore
                                add_error(i + 1, "index_well", f"Well '{row['index_well']}' not found in specified index-kit for i5.", "invalid_value")
                                continue
                            
                            self.library_table.at[idx, "index_i5_sequences"] = ";".join(index_i5_sequences)
                            self.library_table.at[idx, "index_i5_name"] = row["index_well"]
                    else:
                        if len(index_i7_sequences := kit_1_df.loc[(kit_1_df["name"] == row["index_i7"]) & (kit_1_df["type"] == BarcodeType.INDEX_I7), "sequence"].tolist()) == 0:  # type: ignore
                            add_error(i + 1, "index_i7", f"Index i7 '{row['index_i7']}' not found in specified index-kit.", "invalid_value")
                            continue
                        
                        self.library_table.at[idx, "index_i7_sequences"] = ";".join(index_i7_sequences)
                        self.library_table.at[idx, "index_i7_name"] = row["index_i7"]

                        if kit_2.type == IndexType.DUAL_INDEX:
                            if pd.isna(row["index_i5"]):
                                self.df.at[idx, "index_i5"] = row["index_i7"]
                                row["index_i5"] = row["index_i7"]
                                
                            if len(index_i5_sequences := kit_2_df.loc[(kit_2_df["name"] == row["index_i5"]) & (kit_2_df["type"] == BarcodeType.INDEX_I5), "sequence"].tolist()) == 0:  # type: ignore
                                add_error(i + 1, "index_i5", f"Index i5 '{row['index_i5']}' not found in specified index-kit.", "invalid_value")
                                continue
                            
                            self.library_table.at[idx, "index_i5_sequences"] = ";".join(index_i5_sequences)
                            self.library_table.at[idx, "index_i5_name"] = row["index_i5"]
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
            if self.metadata["index_1_kit_id"] is None:
                return list(SASInputForm._feature_mapping_pooled_manual_index.values())
            return list(SASInputForm._feature_mapping_pooled.values())
        raise ValueError("Invalid type")
    
    def columns_mapping(self):
        return dict([(col.name, col.label) for col in self.get_columns()])
    
    def __map_library_types(self):
        library_type_map = {}
        for id, e in LibraryType.as_tuples():
            library_type_map[e.display_name] = id
        
        self.df["library_type_id"] = self.df["library_type"].map(library_type_map)
        self.df["library_name"] = self.df["sample_name"] + self.df["library_type_id"].apply(lambda x: f"_{LibraryType.get(x).identifier}")

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
            self.prepare()
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
            LibraryType.TENX_MULTIPLEXING_CAPTURE.id,
        ]).any():
            cmo_reference_input_form = CMOReferenceInputForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return cmo_reference_input_form.make_response()
        
        if (self.df["library_type_id"].isin([LibraryType.TENX_VISIUM.id, LibraryType.TENX_VISIUM_FFPE.id, LibraryType.TENX_VISIUM_HD.id])).any():
            visium_annotation_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            visium_annotation_form.prepare()
            return visium_annotation_form.make_response()
        
        if LibraryType.TENX_SC_GEX_FLEX.id in self.df["library_type_id"].values:
            frp_annotation_form = FRPAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            frp_annotation_form.prepare()
            return frp_annotation_form.make_response()
    
        sample_annotation_form = SampleAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        sample_annotation_form.prepare()
        return sample_annotation_form.make_response()
