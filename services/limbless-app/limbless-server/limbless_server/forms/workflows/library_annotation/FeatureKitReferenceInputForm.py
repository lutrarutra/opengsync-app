import os
from pathlib import Path
from uuid import uuid4
from typing import Optional, Union, Literal

import pandas as pd
import numpy as np

from flask import Response
from wtforms import SelectField, FileField, FormField, StringField
from wtforms.validators import Optional as OptionalValidator
from flask_wtf.file import FileAllowed
from werkzeug.utils import secure_filename

from limbless_db import models
from limbless_db.core.DBSession import DBSession

from .... import db, logger
from ...TableDataForm import TableDataForm
from ....tools import SpreadSheetColumn
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import OptionalSearchBar
from .FeatureMappingForm import FeatureMappingForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .PoolMappingForm import PoolMappingForm
from .complete_workflow import complete_workflow
from limbless_db.categories import LibraryType


columns = {
    "library_name": SpreadSheetColumn("A", "library_name", "Library Name", "text", 170, str),
    "kit": SpreadSheetColumn("B", "kit", "Kit", "text", 170, str),
    "feature": SpreadSheetColumn("C", "feature", "Feature", "text", 150, str),
    "sequence": SpreadSheetColumn("D", "sequence", "Sequence", "text", 150, str),
    "pattern": SpreadSheetColumn("E", "pattern", "Pattern", "text", 200, str),
    "read": SpreadSheetColumn("F", "read", "Read", "text", 100, str),
}


class FeatureKitReferenceInputForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-7.html"
    
    _required_columns: list[Union[str, list[str]]] = [
    ]
    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    _mapping: dict[str, str] = {
        "Library Name": "library_name",
        "Kit": "kit",
        "Feature": "feature",
        "Sequence": "sequence",
        "Pattern": "pattern",
        "Read": "read",
    }

    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
        "ok": "#82E0AA"
    }

    separator = SelectField(choices=_allowed_extensions, default="tsv", description="Tab-separated ('\\t') or comma-separated (',') file.")
    feature_kit = FormField(OptionalSearchBar, label="1. Select a Predefined Kit for all Feature Capture Libraries", description="All features from this kit will be used for all feature capture libraries in sample annotation sheet.")
    file = FileField(label="File", validators=[FileAllowed([ext for ext, _ in _allowed_extensions])], description="Define custom features or use different predefined kits for each feature capture library.")
    spreadsheet_dummy = StringField(validators=[OptionalValidator()])

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None, input_type: Optional[Literal["predefined", "spreadsheet", "file"]] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid)
        self._context["columns"] = list(columns.values())
        self.input_type = input_type
        self._context["active_tab"] = "help"
        self._context["colors"] = FeatureKitReferenceInputForm.colors
        self.spreadsheet_style = dict()

    def validate(self) -> bool:
        validated = super().validate()

        if self.input_type is None:
            logger.error("Input type not specified in constructor.")
            raise Exception("Input type not specified in constructor.")
        
        self._context["active_tab"] = self.input_type

        if self.input_type == "predefined":
            if self.feature_kit.selected.data is None:
                self.feature_kit.selected.errors = ("Select a feature kit.",)
                return False
        elif self.input_type == "file":
            if self.file.data is None:
                self.file.errors = ("Upload a file.",)
                return False

        if not validated:
            logger.debug(self.errors)
            return False
        
        data = self.get_data()
        library_table: pd.DataFrame = data["library_table"]  # type: ignore

        if self.input_type == "file":
            filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
            filename = secure_filename(filename)
            filepath = os.path.join("uploads", "seq_request", filename)
            self.file.data.save(filepath)

            sep = "\t" if self.separator.data == "tsv" else ","

            try:
                self.feature_table = pd.read_csv(filepath, sep=sep, index_col=False, header=0)
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
            for col in FeatureKitReferenceInputForm._required_columns:
                if col not in self.feature_table.columns:
                    missing.append(col)
            
                if len(missing) > 0:
                    self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                    return False
                
            self.feature_table = self.feature_table.rename(columns=FeatureKitReferenceInputForm._mapping)
            self.feature_table = self.feature_table.replace(r'^\s*$', None, regex=True)
            self.feature_table = self.feature_table.dropna(how="all")

            if len(self.feature_table) == 0:
                self.spreadsheet_dummy.errors = ("File is empty.",)
                return False
            
            if os.path.exists(filepath):
                os.remove(filepath)

        elif self.input_type == "spreadsheet":
            import json
            data = json.loads(self.formdata["spreadsheet"])  # type: ignore
            self.feature_table = pd.DataFrame(data, columns=[col.label for col in columns.values()])
            self.feature_table = self.feature_table.replace(r'^\s*$', None, regex=True)
            self.feature_table = self.feature_table.dropna(how="all")

            if len(self.feature_table) == 0:
                self.spreadsheet_dummy.errors = ("Please fill-out spreadsheet or upload a file.",)
                return False
            
        too_much_specified = (
            (self.feature_table["kit"].notna() & self.feature_table["sequence"].notna()) |
            (self.feature_table["kit"].notna() & self.feature_table["pattern"].notna()) |
            (self.feature_table["kit"].notna() & self.feature_table["read"].notna())
        )
        if too_much_specified.any():
            if self.input_type == "file":
                self.file.errors = ("Columns 'Kit (+ Feature, optional)' or 'Feature + Sequence + Pattern + Read', not both, must be specified for all rows.",)
            else:
                self.spreadsheet_dummy.errors = ("Columns 'Kit (+ Feature, optional)' or 'Feature + Sequence + Pattern + Read', not both, must be specified for all rows.",)

        for i, (_, row) in enumerate(self.feature_table.iterrows()):
            if pd.notna(row["library_name"]) and row["library_name"] not in library_table["library_name"].values:
                if self.input_type == "file":
                    self.file.errors = (f"Row {i+1} has an invalid 'Library Name'.",)
                else:
                    self.spreadsheet_style[f"{columns['library_name'].column}{i+1}"] = f"background-color: {FeatureKitReferenceInputForm.colors['invalid_value']};"
                    self.spreadsheet_dummy.errors = (f"Library Name specified in Row {i+1} is not found in annotation sheet.",)

            kit_feature = pd.notna(row["kit"])
            custom_feature = pd.notna(row["feature"]) & pd.notna(row["sequence"]) & pd.notna(row["pattern"]) & pd.notna(row["read"])
            if not (kit_feature | custom_feature):
                if self.input_type == "file":
                    self.file.errors = (f"Row {i+1} must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified.",)
                else:
                    self.spreadsheet_style[f"{columns['kit'].column}{i+1}"] = f"background-color: {FeatureKitReferenceInputForm.colors['missing_value']};"
                    self.spreadsheet_style[f"{columns['feature'].column}{i+1}"] = f"background-color: {FeatureKitReferenceInputForm.colors['missing_value']};"
                    self.spreadsheet_style[f"{columns['sequence'].column}{i+1}"] = f"background-color: {FeatureKitReferenceInputForm.colors['missing_value']};"
                    self.spreadsheet_style[f"{columns['pattern'].column}{i+1}"] = f"background-color: {FeatureKitReferenceInputForm.colors['missing_value']};"
                    self.spreadsheet_style[f"{columns['read'].column}{i+1}"] = f"background-color: {FeatureKitReferenceInputForm.colors['missing_value']};"
                    self.spreadsheet_dummy.errors = (f"Row {i+1} must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified.",)

        if self.input_type == "file":
            validated = validated and len(self.file.errors) == 0
        elif self.input_type == "spreadsheet":
            validated = validated and (len(self.spreadsheet_dummy.errors) == 0 and len(self.spreadsheet_style) == 0)
        return validated
    
    def __parse(self) -> dict[str, pd.DataFrame | dict]:
        data = self.get_data()
        library_table: pd.DataFrame = data["library_table"]  # type: ignore

        feature_data = {
            "library_name": [],
            "kit": [],
            "feature": [],
            "sequence": [],
            "pattern": [],
            "read": [],
            "kit_id": [],
            "feature_id": [],
        }
        abc_libraries_df = library_table[library_table["library_type_id"] == LibraryType.ANTIBODY_CAPTURE.id]

        if self.input_type == "predefined":
            with DBSession(db) as session:
                kit: models.FeatureKit = session.get_feature_kit(self.feature_kit.selected.data)
                features = kit.features

                for library_name in abc_libraries_df["library_name"]:
                    for feature in features:
                        feature_data["library_name"].append(library_name)
                        feature_data["kit_id"].append(kit.id)
                        feature_data["feature_id"].append(feature.id)
                        feature_data["kit"].append(None)
                        feature_data["feature"].append(None)
                        feature_data["sequence"].append(None)
                        feature_data["pattern"].append(None)
                        feature_data["read"].append(None)

            self.feature_table = pd.DataFrame(feature_data)
        elif self.input_type == "file" or self.input_type == "spreadsheet":
            df = self.feature_table
            
            for _, row in df.iterrows():
                if pd.isna(row["library_name"]):
                    for library_name in abc_libraries_df["library_name"]:
                        feature_data["library_name"].append(library_name)
                        feature_data["kit"].append(row["kit"])
                        feature_data["feature"].append(row["feature"])
                        feature_data["sequence"].append(row["sequence"])
                        feature_data["pattern"].append(row["pattern"])
                        feature_data["read"].append(row["read"])
                        feature_data["kit_id"].append(None)
                        feature_data["feature_id"].append(None)
                else:
                    feature_data["library_name"].append(row["library_name"])
                    feature_data["kit"].append(row["kit"])
                    feature_data["feature"].append(row["feature"])
                    feature_data["sequence"].append(row["sequence"])
                    feature_data["pattern"].append(row["pattern"])
                    feature_data["read"].append(row["read"])
                    feature_data["kit_id"].append(None)
                    feature_data["feature_id"].append(None)

        self.feature_table = pd.DataFrame(feature_data)
        data["feature_table"] = self.feature_table
        self.update_data(data)

        return data
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            if self.input_type == "spreadsheet":
                self._context["spreadsheet_style"] = self.spreadsheet_style
                context["spreadsheet_data"] = self.feature_table.replace(np.nan, "").values.tolist()
                if context["spreadsheet_data"] == []:
                    context["spreadsheet_data"] = [[None]]
            return self.make_response(**context)

        data = self.__parse()
        library_table: pd.DataFrame = data["library_table"]  # type: ignore
        feature_table: pd.DataFrame = data["feature_table"]  # type: ignore
        
        if not self.feature_kit.selected.data and (~feature_table["kit"].isna()).any():
            feature_kit_mapping_form = FeatureMappingForm(uuid=self.uuid)
            context = feature_kit_mapping_form.prepare(data) | context
            return feature_kit_mapping_form.make_response(**context)
        
        if (library_table["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id).any():
            visium_annotation_form = VisiumAnnotationForm(uuid=self.uuid)
            return visium_annotation_form.make_response(**context)

        if "pool" in library_table.columns:
            pool_mapping_form = PoolMappingForm(uuid=self.uuid)
            context = pool_mapping_form.prepare(data) | context
            return pool_mapping_form.make_response(**context)

        return complete_workflow(self, user_id=context["user_id"], seq_request=context["seq_request"])
        
