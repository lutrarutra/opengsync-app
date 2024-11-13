import os
from pathlib import Path
from uuid import uuid4
from typing import Optional, Literal

import pandas as pd
import numpy as np

from flask import Response
from wtforms import SelectField, FileField, StringField
from wtforms.validators import Optional as OptionalValidator
from flask_wtf.file import FileAllowed
from werkzeug.utils import secure_filename

from limbless_db import models
from limbless_db.categories import LibraryType, FeatureType

from .... import logger, tools
from ....tools import SpreadSheetColumn
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm
from .KitMappingForm import KitMappingForm
from .FeatureReferenceInputForm import FeatureReferenceInputForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FRPAnnotationForm import FRPAnnotationForm
from .SampleAnnotationForm import SampleAnnotationForm


class CMOReferenceInputForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-6.html"
    columns = {
        "demux_name": SpreadSheetColumn("A", "demux_name", "Demultiplexing Name", "text", 170, str),
        "sample_name": SpreadSheetColumn("B", "sample_name", "Sample Name", "text", 170, str),
        "kit": SpreadSheetColumn("C", "kit", "Kit", "text", 170, str),
        "feature": SpreadSheetColumn("D", "feature", "Feature", "text", 150, str),
        "sequence": SpreadSheetColumn("E", "sequence", "Sequence", "text", 150, str),
        "pattern": SpreadSheetColumn("F", "pattern", "Pattern", "text", 200, str),
        "read": SpreadSheetColumn("G", "read", "Read", "text", 100, str),
    }
    
    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    _mapping: dict[str, str] = dict([(col.name, col.label) for col in columns.values()])
    _required_columns: list[str] = [col.name for col in columns.values()]

    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
        "invalid_input": "#AED6F1"
    }

    separator = SelectField(choices=_allowed_extensions, default="tsv")
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])
    spreadsheet_dummy = StringField(validators=[OptionalValidator()])

    def __init__(self, seq_request: models.SeqRequest, previous_form: Optional[TableDataForm] = None, formdata: dict = {}, uuid: Optional[str] = None, input_type: Optional[Literal["spreadsheet", "file"]] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid, previous_form=previous_form)
        self.seq_request = seq_request
        self.input_type = input_type
        self._context["columns"] = CMOReferenceInputForm.columns.values()
        self._context["active_tab"] = "help"
        self._context["colors"] = CMOReferenceInputForm.colors
        self._context["seq_request"] = seq_request
        self.spreadsheet_style = dict()

    def validate(self) -> bool:
        validated = super().validate()

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
        
        if self.input_type == "file":
            filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
            filename = secure_filename(filename)
            filepath = os.path.join("uploads", "seq_request", filename)
            self.file.data.save(filepath)

            sep = "\t" if self.separator.data == "tsv" else ","

            try:
                self.cmo_table = pd.read_csv(filepath, sep=sep, index_col=False, header=0)
                validated = True
            except pd.errors.ParserError as e:
                self.file.errors = (str(e),)
                validated = False
            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)
                if not validated:
                    return False
            
            missing = []
            for col in CMOReferenceInputForm._required_columns:
                if col not in self.cmo_table.columns:
                    missing.append(col)
            
                if len(missing) > 0:
                    self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                    return False
                
            self.cmo_table = self.cmo_table.rename(columns=CMOReferenceInputForm._mapping)
            self.cmo_table = self.cmo_table.replace(r'^\s*$', None, regex=True)
            self.cmo_table = self.cmo_table.dropna(how="all")

            if len(self.cmo_table) == 0:
                self.file.errors = ("File is empty.",)
                return False

        elif self.input_type == "spreadsheet":
            import json
            data = json.loads(self.formdata["spreadsheet"])  # type: ignore
            try:
                self.cmo_table = pd.DataFrame(data)
            except ValueError as e:
                self.spreadsheet_dummy.errors = (str(e),)
                return False
            
            columns = list(CMOReferenceInputForm.columns.keys())
            if len(self.cmo_table.columns) != len(columns):
                self.spreadsheet_dummy.errors = (f"Invalid number of columns (expected {len(columns)}). Do not insert new columns or rearrange existing columns.",)
                return False
            
            self.cmo_table.columns = columns
            self.cmo_table = self.cmo_table.replace(r'^\s*$', None, regex=True)
            self.cmo_table = self.cmo_table.dropna(how="all")

            if len(self.cmo_table) == 0:
                self.spreadsheet_dummy.errors = ("Please fill-out spreadsheet or upload a file.",)
                return False
        
        library_table: pd.DataFrame = self.tables["library_table"]

        self.file.errors = []
        self.spreadsheet_dummy.errors = []

        self.cmo_table["sample_name"] = self.cmo_table["sample_name"].apply(lambda x: tools.make_alpha_numeric(x))
        self.cmo_table["sequence"] = self.cmo_table["sequence"].apply(lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with=None))
        self.cmo_table["pattern"] = self.cmo_table["pattern"].apply(lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with=None))
        self.cmo_table["read"] = self.cmo_table["read"].apply(lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with=None))
        kit_feature = pd.notna(self.cmo_table["kit"]) & pd.notna(self.cmo_table["feature"])
        custom_feature = pd.notna(self.cmo_table["sequence"]) & pd.notna(self.cmo_table["pattern"]) & pd.notna(self.cmo_table["read"])
        invalid_feature = (pd.notna(self.cmo_table["kit"]) | pd.notna(self.cmo_table["feature"])) & (pd.notna(self.cmo_table["sequence"]) | pd.notna(self.cmo_table["pattern"]) | pd.notna(self.cmo_table["read"]))

        errors = []
        
        def add_error(row_num: int, column: str, message: str, color: Literal["missing_value", "invalid_value", "duplicate_value", "invalid_input"]):
            msg = f"Row {row_num}: {message}"
            if msg not in errors:
                errors.append(msg)
            if self.input_type == "spreadsheet":
                self.spreadsheet_style[f"{CMOReferenceInputForm.columns[column].column}{row_num}"] = f"background-color: {CMOReferenceInputForm.colors[color]};"
                self.spreadsheet_dummy.errors = errors
            else:
                self.file.errors = errors

        for i, (idx, row) in enumerate(self.cmo_table.iterrows()):
            # sample name not defined
            if pd.isna(row["sample_name"]):
                add_error(i + 1, "sample_name", "'Sample Name' must be specified.", "missing_value")

            # sample name not found in library table
            elif row["sample_name"] not in library_table["sample_name"].values:
                add_error(i + 1, "sample_name", f"'Sample Name' must be one of: [{', '.join(set(library_table['sample_name'].values.tolist()))}]", "invalid_value")

            # Demux name not defined
            if pd.isna(row["demux_name"]):
                add_error(i + 1, "demux_name", "'Demux Name' must be specified.", "missing_value")

            # Not defined custom nor kit feature
            if (not custom_feature.at[idx] and not kit_feature.at[idx]):
                add_error(i + 1, "kit", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "missing_value")
                add_error(i + 1, "feature", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "missing_value")
                add_error(i + 1, "sequence", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "missing_value")
                add_error(i + 1, "pattern", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "missing_value")
                add_error(i + 1, "read", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "missing_value")

            # Defined both custom and kit feature
            elif custom_feature.at[idx] and kit_feature.at[idx]:
                add_error(i + 1, "kit", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")
                add_error(i + 1, "feature", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")
                add_error(i + 1, "sequence", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")
                add_error(i + 1, "pattern", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")
                add_error(i + 1, "read", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")

            elif invalid_feature.at[idx]:
                if pd.notna(row["kit"]):
                    add_error(i + 1, "kit", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")
                if pd.notna(row["feature"]):
                    add_error(i + 1, "feature", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")
                if pd.notna(row["sequence"]):
                    add_error(i + 1, "sequence", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")
                if pd.notna(row["pattern"]):
                    add_error(i + 1, "pattern", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")
                if pd.notna(row["read"]):
                    add_error(i + 1, "read", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")

            # Duplicate custom feature in sample
            # elif custom_feature.at[idx]:
            #     idx_sample_name = self.cmo_table["sample_name"] == row["sample_name"]
            #     idx_sequence = self.cmo_table["sequence"] == row["sequence"]
            #     idx_pattern = self.cmo_table["pattern"] == row["pattern"]
            #     idx_read = self.cmo_table["read"] == row["read"]

            #     idx = idx_sequence & idx_pattern & idx_read
            #     if pd.notna(row["sample_name"]):
            #         idx = idx & idx_sample_name

            #     if self.cmo_table[idx].shape[0] > 1:
            #         add_error(i + 1, "sequence", f"Row {i+1} has duplicate 'Sequence + Pattern + Read' combination in same sample.", "duplicate_value")

            # Duplicate kit feature in sample
            # elif kit_feature.at[idx]:
            #     idx_sample_name = self.cmo_table["sample_name"] == row["sample_name"]
            #     idx_kit = self.cmo_table["kit"] == row["kit"]
            #     idx_feature = self.cmo_table["feature"] == row["feature"]
            #     idx = True
            #     if pd.notna(row["sample_name"]):
            #         idx = idx & idx_sample_name
            #     if pd.notna(row["kit"]):
            #         idx = idx & idx_kit
            #     if pd.notna(row["feature"]):
            #         idx = idx & idx_feature
                
            #     if self.cmo_table[idx].shape[0] > 1:
            #         add_error(i + 1, "kit", f"Row {i+1} has duplicate 'Kit' + 'Feature' specified for same sample.", "duplicate_value")

        if self.input_type == "file":
            validated = validated and len(self.file.errors) == 0
        elif self.input_type == "spreadsheet":
            validated = validated and (len(self.spreadsheet_dummy.errors) == 0 and len(self.spreadsheet_style) == 0)

        if validated:
            self.cmo_table["custom_feature"] = custom_feature
            self.cmo_table["kit_feature"] = kit_feature
        return validated
    
    def process_request(self) -> Response:
        if not self.validate():
            if self.input_type == "spreadsheet":
                self._context["spreadsheet_style"] = self.spreadsheet_style
                self._context["spreadsheet_data"] = self.cmo_table.replace(np.nan, "").values.tolist()
                if self._context["spreadsheet_data"] == []:
                    self._context["spreadsheet_data"] = [[None]]
            return self.make_response()

        library_table = self.tables["library_table"]

        kit_table = self.cmo_table[self.cmo_table["kit"].notna()][["kit"]].drop_duplicates().copy()
        kit_table["type_id"] = FeatureType.CMO.id
        kit_table["kit_id"] = None

        if kit_table.shape[0] > 0:
            if (existing_kit_table := self.tables.get("kit_table")) is None:  # type: ignore
                self.add_table("kit_table", kit_table)
            else:
                kit_table = pd.concat([kit_table, existing_kit_table])
                self.update_table("kit_table", kit_table, update_data=False)
        
        self.add_table("cmo_table", self.cmo_table)
        self.update_data()

        if (library_table["library_type_id"] == LibraryType.TENX_ANTIBODY_CAPTURE.id).any():
            feature_reference_input_form = FeatureReferenceInputForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return feature_reference_input_form.make_response()

        if kit_table["kit_id"].isna().any():
            feature_kit_mapping_form = KitMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            feature_kit_mapping_form.prepare()
            return feature_kit_mapping_form.make_response()
        
        if (library_table["library_type_id"].isin([LibraryType.TENX_VISIUM.id, LibraryType.TENX_VISIUM_FFPE.id, LibraryType.TENX_VISIUM_HD.id])).any():
            visium_annotation_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            visium_annotation_form.prepare()
            return visium_annotation_form.make_response()
        
        if LibraryType.TENX_SC_GEX_FLEX.id in library_table["library_type_id"].values:
            frp_annotation_form = FRPAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            frp_annotation_form.prepare()
            return frp_annotation_form.make_response()

        sample_annotation_form = SampleAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return sample_annotation_form.make_response()