import os
from pathlib import Path
from uuid import uuid4
from typing import Optional, Union

import pandas as pd

from flask import Response
from wtforms import SelectField, FileField, FormField
from flask_wtf.file import FileAllowed
from werkzeug.utils import secure_filename

from limbless_db import models
from limbless_db.core.DBSession import DBSession

from .... import db, logger
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import OptionalSearchBar
from .FeatureKitMappingForm import FeatureKitMappingForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .PoolMappingForm import PoolMappingForm
from .BarcodeCheckForm import BarcodeCheckForm
from limbless_db.categories import LibraryType


class FeatureKitReferenceInputForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-6.2.html"
    
    _required_columns: list[Union[str, list[str]]] = [
    ]
    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    _mapping: dict[str, str] = {
        "Library Name": "library_name",
        "Kit": "kit",
        "Feature": "feature_name",
        "Sequence": "sequence",
        "Pattern": "pattern",
        "Read": "read",
    }

    separator = SelectField(choices=_allowed_extensions, default="tsv", description="Tab-separated ('\\t') or comma-separated (',') file.")
    feature_kit = FormField(OptionalSearchBar, label="1. Select Predefined Kit for all Feature Caputre Libraries", description="All features from this kit will be used for all feature capture libraries in sample annotation sheet.")
    file = FileField(label="2/3. File with custom features", validators=[FileAllowed([ext for ext, _ in _allowed_extensions])], description="Define custom features or use different predefined kits for each feature capture library.")

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, uuid=uuid)

    def prepare(self, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.get_data()

        # self.update_data(data)
        return {}

    def validate(self) -> bool:
        if not super().validate():
            return False

        if self.feature_kit.selected.data and self.file.data:
            self.file.errors = ("Upload a file or specify common kit, not both.",)
            self.feature_kit.selected.errors = ("Upload a file or specify common kit, not both.",)
            return False
        
        if self.file.data is None and self.feature_kit.selected.data is None:
            self.file.errors = ("Upload a file or specify common kit.",)
            self.feature_kit.selected.errors = ("Upload a file or specify common kit.",)
            return False
        
        if self.file.data is not None:
            filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
            filename = secure_filename(filename)
            filepath = os.path.join("uploads", "seq_request", filename)
            self.file.data.save(filepath)

            sep = "\t" if self.separator.data == "tsv" else ","

            try:
                self.feature_ref = pd.read_csv(filepath, sep=sep, index_col=False, header=0)
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
                if col not in self.feature_ref.columns:
                    missing.append(col)
            
                if len(missing) > 0:
                    self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                    return False
            
            data = self.get_data()

            too_much_specified = (
                (self.feature_ref["Kit"].notna() & self.feature_ref["Sequence"].notna()) |
                (self.feature_ref["Kit"].notna() & self.feature_ref["Pattern"].notna()) |
                (self.feature_ref["Kit"].notna() & self.feature_ref["Read"].notna())
            )
            if too_much_specified.any():
                self.file.errors = ("Columns 'Kit (+ Feature, optional)' or 'Feature + Sequence + Pattern + Read', not both, must be specified for all rows.",)
                return False

            libraries_not_mapped = ~self.feature_ref["Library Name"].isin(data["library_table"]["library_name"])
            if libraries_not_mapped.any() and self.feature_ref["Library Name"].notna().any():
                unmapped = self.feature_ref["Library Name"][libraries_not_mapped].unique().tolist()
                self.file.errors = (
                    "Values in 'Library Name'-column in feature reference must be found in 'Sample Name'-column of sample annotation sheet." + ", ".join(unmapped),
                )
                return False
            
            specified_with_name = ~self.feature_ref["Kit"].isna()
            specified_manually = (~self.feature_ref["Feature"].isna() & ~self.feature_ref["Sequence"].isna() & ~self.feature_ref["Pattern"].isna() & ~self.feature_ref["Read"].isna())
            if (~(specified_with_name | specified_manually)).any():
                self.file.errors = ("Columns 'Kit + Feature' or 'Sequence + Pattern Read'  must be specified for all rows.",)
                return False
        return True
    
    def __parse(self) -> dict[str, pd.DataFrame]:
        data = self.get_data()

        if self.feature_kit.selected.data:
            feature_ref = {
                "library_name": [],
                "feature_id": [],
                "feature_kit_id": [],
            }
            with DBSession(db) as session:
                kit: models.FeatureKit = session.get_feature_kit(self.feature_kit.selected.data)
                features = kit.features

                _df = self.get_data()["library_table"]
                _df = _df[_df["library_type_id"] == LibraryType.ANTIBODY_CAPTURE.id]

                for library_name in _df["library_name"]:
                    for feature in features:
                        feature_ref["library_name"].append(library_name)
                        feature_ref["feature_kit_id"].append(kit.id)
                        feature_ref["feature_id"].append(feature.id)

            self.feature_ref = pd.DataFrame(feature_ref)
        else:
            self.feature_ref = self.feature_ref.rename(columns=FeatureKitReferenceInputForm._mapping)
            if "feature_id" not in self.feature_ref.columns:
                self.feature_ref["feature_id"] = None

        data["feature_table"] = self.feature_ref

        self.update_data(data)

        return data
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)

        data = self.__parse()
        
        if not self.feature_kit.selected.data and (~data["feature_table"]["kit"].isna()).any():
            feature_kit_mapping_form = FeatureKitMappingForm(uuid=self.uuid)
            context = feature_kit_mapping_form.prepare(data) | context
            return feature_kit_mapping_form.make_response(**context)
        
        if (data["library_table"]["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id).any():
            visium_annotation_form = VisiumAnnotationForm(uuid=self.uuid)
            return visium_annotation_form.make_response(**context)

        if "pool" in data["library_table"].columns:
            pool_mapping_form = PoolMappingForm(uuid=self.uuid)
            context = pool_mapping_form.prepare(data) | context
            return pool_mapping_form.make_response(**context)

        barcode_check_form = BarcodeCheckForm(uuid=self.uuid)
        context = barcode_check_form.prepare(data)
        return barcode_check_form.make_response(**context)
        
