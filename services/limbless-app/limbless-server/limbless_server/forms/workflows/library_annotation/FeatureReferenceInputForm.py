import os
from pathlib import Path
from uuid import uuid4
from typing import Optional, Literal

import pandas as pd
import numpy as np

from flask import Response
from wtforms import SelectField, FileField, FormField, StringField
from wtforms.validators import Optional as OptionalValidator
from flask_wtf.file import FileAllowed
from werkzeug.utils import secure_filename

from limbless_db import models
from limbless_db.core.DBSession import DBSession
from limbless_db.categories import LibraryType, FeatureType

from .... import db, logger, tools
from ...TableDataForm import TableDataForm
from ....tools import SpreadSheetColumn
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import OptionalSearchBar
from .KitMappingForm import KitMappingForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .PoolMappingForm import PoolMappingForm
from .CompleteSASForm import CompleteSASForm


class FeatureReferenceInputForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-7.html"

    columns = {
        "library_name": SpreadSheetColumn("A", "library_name", "Library Name", "text", 170, str),
        "kit": SpreadSheetColumn("B", "kit", "Kit", "text", 170, str),
        "feature": SpreadSheetColumn("C", "feature", "Feature", "text", 150, str),
        "sequence": SpreadSheetColumn("D", "sequence", "Sequence", "text", 150, str),
        "pattern": SpreadSheetColumn("E", "pattern", "Pattern", "text", 200, str),
        "read": SpreadSheetColumn("F", "read", "Read", "text", 100, str),
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

    separator = SelectField(choices=_allowed_extensions, default="tsv", description="Tab-separated ('\\t') or comma-separated (',') file.")
    feature_kit = FormField(OptionalSearchBar, label="1. Select a Predefined Kit for all Feature Capture Libraries", description="All features from this kit will be used for all feature capture libraries in sample annotation sheet.")
    file = FileField("File", validators=[FileAllowed([ext for ext, _ in _allowed_extensions])], description="Define custom features or use different predefined kits for each feature capture library.")
    spreadsheet_dummy = StringField(validators=[OptionalValidator()])

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None, input_type: Optional[Literal["predefined", "spreadsheet", "file"]] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid)
        self.input_type = input_type
        self._context["columns"] = FeatureReferenceInputForm.columns.values()
        self._context["active_tab"] = "help"
        self._context["colors"] = FeatureReferenceInputForm.colors
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
            else:
                return True
        elif self.input_type == "file":
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
            for col in FeatureReferenceInputForm._required_columns:
                if col not in self.feature_table.columns:
                    missing.append(col)
            
                if len(missing) > 0:
                    self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                    return False
                
            self.feature_table = self.feature_table.rename(columns=FeatureReferenceInputForm._mapping)
            self.feature_table = self.feature_table.replace(r'^\s*$', None, regex=True)
            self.feature_table = self.feature_table.dropna(how="all")

            if len(self.feature_table) == 0:
                self.file.errors = ("File is empty.",)
                return False
            
            if os.path.exists(filepath):
                os.remove(filepath)

        elif self.input_type == "spreadsheet":
            import json
            data = json.loads(self.formdata["spreadsheet"])  # type: ignore
            self.feature_table = pd.DataFrame(data, columns=[col.label for col in FeatureReferenceInputForm.columns.values()])
            self.feature_table = self.feature_table.replace(r'^\s*$', None, regex=True)
            self.feature_table = self.feature_table.dropna(how="all")

            if len(self.feature_table) == 0:
                self.spreadsheet_dummy.errors = ("Please fill-out spreadsheet or upload a file.",)
                return False
            
        data = self.get_data()
        library_table: pd.DataFrame = data["library_table"]  # type: ignore
        abc_libraries = library_table[library_table["library_type_id"] == LibraryType.ANTIBODY_CAPTURE.id]
            
        self.file.errors = []
        self.spreadsheet_dummy.errors = []

        self.feature_table["library_name"] = self.feature_table["library_name"].apply(lambda x: tools.make_alpha_numeric(x))
        self.feature_table["sequence"] = self.feature_table["sequence"].apply(lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with=None))
        self.feature_table["pattern"] = self.feature_table["pattern"].apply(lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with=None))
        self.feature_table["read"] = self.feature_table["read"].apply(lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with=None))
        self.feature_table["kit_feature"] = pd.notna(self.feature_table["kit"])
        self.feature_table["custom_feature"] = pd.notna(self.feature_table["feature"]) & pd.notna(self.feature_table["sequence"]) & pd.notna(self.feature_table["pattern"]) & pd.notna(self.feature_table["read"])
        self.feature_table["invalid_feature"] = pd.notna(self.feature_table["kit"]) & (pd.notna(self.feature_table["sequence"]) | pd.notna(self.feature_table["pattern"]) | pd.notna(self.feature_table["read"]))
        self.feature_table["duplicated"] = self.feature_table.duplicated(keep=False)
            
        # If ABC library is not mentioned in the feature table, i.e. no features assigned to it
        mentioned_abc_libraries = abc_libraries["library_name"].isin(self.feature_table["library_name"])
        if pd.notna(self.feature_table["library_name"]).any() and not mentioned_abc_libraries.all():
            unmentioned = abc_libraries[~mentioned_abc_libraries]["library_name"].values.tolist()
            if self.input_type == "file":
                self.file.errors.append(f"No features assigned to libraries: {unmentioned}")
            else:
                self.spreadsheet_dummy.errors.append(f"No features assigned to libraries: {unmentioned}")

            return False

        for i, (_, row) in enumerate(self.feature_table.iterrows()):
            if row["duplicated"]:
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i+1} is a duplicate.")
                else:
                    for col in FeatureReferenceInputForm.columns.values():
                        self.spreadsheet_style[f"{col.column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['duplicate_value']};"
                    self.spreadsheet_dummy.errors.append(f"Row {i+1} is a duplicate.")

            if pd.notna(row["library_name"]) and row["library_name"] not in abc_libraries["library_name"].values:
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i+1} has an invalid 'Library Name'.")
                else:
                    self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['library_name'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['invalid_value']};"
                    self.spreadsheet_dummy.errors.append(f"Library Name specified in Row {i+1} is not found in annotation sheet (must be of type Antibody Capture).")

            if row["invalid_feature"]:
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i+1} must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.")
                else:
                    for col in FeatureReferenceInputForm.columns.values():
                        if col.label == "library_name":
                            continue
                        if pd.notna(row[col.label]):
                            self.spreadsheet_style[f"{col.column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['invalid_input']};"
                    self.spreadsheet_dummy.errors.append(f"Row {i+1} must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.")
            elif (not row["custom_feature"] and not row["kit_feature"]):
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i+1} must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.")
                else:
                    self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['kit'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['missing_value']};"
                    self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['feature'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['missing_value']};"
                    self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['sequence'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['missing_value']};"
                    self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['pattern'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['missing_value']};"
                    self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['read'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['missing_value']};"
                    self.spreadsheet_dummy.errors.append(f"Row {i+1} must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.")
            elif row["custom_feature"] and row["kit_feature"]:
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i+1} must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both.")
                else:
                    self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['kit'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['invalid_value']};"
                    self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['feature'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['invalid_value']};"
                    self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['sequence'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['invalid_value']};"
                    self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['pattern'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['invalid_value']};"
                    self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['read'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['invalid_value']};"
                    self.spreadsheet_dummy.errors.append(f"Row {i+1} must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both.")
            elif row["custom_feature"]:
                idx_library_name = self.feature_table["library_name"] == row["library_name"]
                idx_sequence = self.feature_table["sequence"] == row["sequence"]
                idx_pattern = self.feature_table["pattern"] == row["pattern"]
                idx_read = self.feature_table["read"] == row["read"]

                idx = idx_sequence & idx_pattern & idx_read
                if pd.notna(row["library_name"]):
                    idx = idx & idx_library_name

                if self.feature_table[idx].shape[0] > 1:
                    if self.input_type == "file":
                        self.file.errors.append(f"Row {i+1} has duplicate 'Sequence + Pattern + Read' combination in same library.")
                    else:
                        self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['sequence'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['duplicate_value']};"
                        self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['pattern'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['duplicate_value']};"
                        self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['read'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['duplicate_value']};"
                        self.spreadsheet_dummy.errors.append(f"Row {i+1} has duplicate 'Sequence + Pattern + Read' combination in same library.")
            elif row["kit_feature"]:
                idx_library_name = self.feature_table["library_name"] == row["library_name"]
                idx_kit = self.feature_table["kit"] == row["kit"]
                idx_feature = self.feature_table["feature"] == row["feature"]
                idx = True
                if pd.notna(row["library_name"]):
                    idx = idx & idx_library_name
                if pd.notna(row["kit"]):
                    idx = idx & idx_kit
                if pd.notna(row["feature"]):
                    idx = idx & idx_feature
                
                if self.feature_table[idx].shape[0] > 1:
                    if self.input_type == "file":
                        self.file.errors.append(f"Row {i+1} has duplicate 'Kit' + 'Feature' specified for same library.")
                    else:
                        self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['kit'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['duplicate_value']};"
                        if pd.notna(row["library_name"]):
                            self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['library_name'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['duplicate_value']};"
                        if pd.notna(row["feature"]):
                            self.spreadsheet_style[f"{FeatureReferenceInputForm.columns['feature'].column}{i+1}"] = f"background-color: {FeatureReferenceInputForm.colors['duplicate_value']};"
                        self.spreadsheet_dummy.errors.append(f"Row {i+1} has duplicate 'Kit' + 'Feature' specified for same library.")

        if self.input_type == "file":
            validated = validated and len(self.file.errors) == 0
        elif self.input_type == "spreadsheet":
            validated = validated and (len(self.spreadsheet_dummy.errors) == 0 and len(self.spreadsheet_style) == 0)
        return validated

    def process_request(self, **context) -> Response:
        if not self.validate():
            if self.input_type == "spreadsheet":
                self._context["spreadsheet_style"] = self.spreadsheet_style
                context["spreadsheet_data"] = self.feature_table[FeatureReferenceInputForm.columns.keys()].replace(np.nan, "").values.tolist()
                if context["spreadsheet_data"] == []:
                    context["spreadsheet_data"] = [[None]]
            return self.make_response(**context)

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

        def add_feature(
            library_name: str, feature_name: str,
            sequence: str, pattern: str, read: str,
            kit_name: Optional[str],
            kit_id: Optional[int] = None,
            feature_id: Optional[int] = None
        ):
            feature_data["library_name"].append(library_name)
            feature_data["kit_id"].append(kit_id)
            feature_data["feature_id"].append(feature_id)
            feature_data["kit"].append(kit_name)
            feature_data["feature"].append(feature_name)
            feature_data["sequence"].append(sequence)
            feature_data["pattern"].append(pattern)
            feature_data["read"].append(read)

        if self.input_type == "predefined":
            with DBSession(db) as session:
                kit: models.FeatureKit = session.get_feature_kit(self.feature_kit.selected.data)
                features = kit.features

                for library_name in abc_libraries_df["library_name"]:
                    for feature in features:
                        add_feature(
                            library_name=library_name,
                            kit_id=kit.id,
                            kit_name=kit.name,
                            feature_id=feature.id,
                            feature_name=feature.name,
                            sequence=feature.sequence,
                            pattern=feature.pattern,
                            read=feature.read
                        )

            self.feature_table = pd.DataFrame(feature_data)
        elif self.input_type == "file" or self.input_type == "spreadsheet":
            for _, row in self.feature_table.iterrows():
                if pd.isna(row["library_name"]):
                    for library_name in abc_libraries_df["library_name"]:
                        add_feature(
                            library_name=library_name,
                            kit_name=row["kit"],
                            feature_name=row["feature"],
                            sequence=row["sequence"],
                            pattern=row["pattern"],
                            read=row["read"]
                        )
                else:
                    add_feature(
                        library_name=row["library_name"],
                        kit_name=row["kit"],
                        feature_name=row["feature"],
                        sequence=row["sequence"],
                        pattern=row["pattern"],
                        read=row["read"]
                    )

        self.feature_table = pd.DataFrame(feature_data)

        kit_table: pd.DataFrame
        if (kit_table := data.get("kit_table")) is None:  # type: ignore
            kit_table = self.feature_table[["kit", "kit_id"]].drop_duplicates().copy()
            kit_table["type_id"] = FeatureType.ANTIBODY.id
        else:
            _kit_table = self.feature_table[["kit", "kit_id"]].drop_duplicates().copy()
            _kit_table["type_id"] = FeatureType.ANTIBODY.id
            kit_table = pd.concat([kit_table, _kit_table])

        data["feature_table"] = self.feature_table
        data["kit_table"] = kit_table
        self.update_data(data)
        
        if kit_table["kit_id"].notna().any():
            feature_kit_mapping_form = KitMappingForm(uuid=self.uuid)
            feature_kit_mapping_form.prepare(data)
            return feature_kit_mapping_form.make_response(**context)
        
        if (library_table["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id).any():
            visium_annotation_form = VisiumAnnotationForm(uuid=self.uuid)
            return visium_annotation_form.make_response(**context)

        if "pool" in library_table.columns:
            pool_mapping_form = PoolMappingForm(uuid=self.uuid)
            pool_mapping_form.prepare(data)
            return pool_mapping_form.make_response(**context)

        complete_sas_form = CompleteSASForm(uuid=self.uuid)
        complete_sas_form.prepare(data)
        return complete_sas_form.make_response(**context)
        
