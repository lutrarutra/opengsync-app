from typing import Optional
from flask import Response
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator

from limbless_db.categories import LibraryType

from .... import db, logger
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import SearchBar
from .PoolMappingForm import PoolMappingForm
from .BarcodeCheckForm import BarcodeCheckForm
from .VisiumAnnotationForm import VisiumAnnotationForm


class FeatureMappingSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    feature_kit = FormField(SearchBar, label="Select Feature Kit")


class FeatureMappingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-7.html"

    input_fields = FieldList(FormField(FeatureMappingSubForm), min_entries=1)

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid)

    def validate(self) -> bool:
        validated = super().validate()
        if not validated:
            return False
        
        data = self.get_data()
        if (cmo_table := data.get("cmo_table")) is not None:
            kits = cmo_table["kit"].unique().tolist()
            kits = [feature_kit if feature_kit and not pd.isna(feature_kit) else None for feature_kit in kits]
            
            for i, entry in enumerate(self.input_fields):
                raw_feature_kit_label = kits[i]
                feature_kit_search_field: SearchBar = entry.feature_kit  # type: ignore

                if (feature_kit_id := feature_kit_search_field.selected.data) is None:
                    feature_kit_search_field.selected.errors = ("Not valid feature kit selected")
                    return False
                
                if (selected_kit := db.get_feature_kit(feature_kit_id)) is None:
                    feature_kit_search_field.selected.errors = ("Not valid feature kit selected")
                    return False
                
                _df = cmo_table[cmo_table["kit"] == raw_feature_kit_label]
                for _, row in _df.iterrows():
                    feature_name = str(row["feature_name"])
                    if (_ := db.get_feature_from_kit_by_feature_name(feature_name, selected_kit.id)) is None:
                        feature_kit_search_field.selected.errors = (f"Unknown feature '{feature_name}' does not belong to this feature kit.",)
                        return False
        
        if (feature_table := data.get("feature_table")) is not None:
            kits = feature_table["kit"].unique().tolist()
            kits = [feature_kit if feature_kit and not pd.isna(feature_kit) else None for feature_kit in kits]

            for i, entry in enumerate(self.input_fields):
                raw_feature_kit_label = kits[i]
                feature_kit_search_field: SearchBar = entry.feature_kit  # type: ignore

                if (feature_kit_id := feature_kit_search_field.selected.data) is None:
                    feature_kit_search_field.selected.errors = ("Not valid feature kit selected")
                    return False
                
                if (selected_kit := db.get_feature_kit(feature_kit_id)) is None:
                    feature_kit_search_field.selected.errors = ("Not valid feature kit selected")
                    return False

        return validated
    
    def prepare(self, data: Optional[dict[str, pd.DataFrame | dict]] = None) -> dict:
        if data is None:
            data = self.get_data()

        feature_table: pd.DataFrame = data["feature_table"]  # type: ignore

        kits = feature_table["kit"].unique().tolist()
        kits = [feature_kit if feature_kit and not pd.isna(feature_kit) else None for feature_kit in kits]

        for i, raw_feature_kit_label in enumerate(kits):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields[i]
            feature_kit_search_field: SearchBar = entry.feature_kit  # type: ignore
            entry.raw_label.data = raw_feature_kit_label

            if raw_feature_kit_label is None:
                selected_kit = None
            elif feature_kit_search_field.selected.data is None:
                selected_kit = next(iter(db.query_feature_kits(raw_feature_kit_label, 1)), None)
                feature_kit_search_field.selected.data = selected_kit.id if selected_kit else None
                feature_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None
            else:
                selected_kit = db.get_feature_kit(feature_kit_search_field.selected.data)
                feature_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None

        self.update_data(data)

        return {}
    
    def __parse(self) -> dict[str, pd.DataFrame | dict]:
        data = self.get_data()
        library_table: pd.DataFrame = data["library_table"]  # type: ignore
        feature_table: pd.DataFrame = data["feature_table"]  # type: ignore

        kits = feature_table["kit"].unique().tolist()
        kits = [feature_kit if feature_kit and not pd.isna(feature_kit) else None for feature_kit in kits]

        feature_table["feature_kit_name"] = None
        feature_table["feature_kit_id"] = None

        for i, feature_kit in enumerate(kits):
            entry = self.input_fields[i]
            feature_kit_search_field: SearchBar = entry.feature_kit  # type: ignore

            if (selected_id := feature_kit_search_field.selected.data) is not None:
                if (selected_kit := db.get_feature_kit(selected_id)) is None:
                    logger.error(f"Feature kit with id '{selected_id}' does not exist.")
                    raise Exception(f"Feature kit with id '{selected_id}' does not exist.")
                
                feature_table.loc[feature_table["kit"] == feature_kit, "feature_kit_id"] = selected_id
                feature_table.loc[feature_table["kit"] == feature_kit, "feature_kit_name"] = selected_kit.name

            else:
                raise Exception("Feature kit not selected.")
            
        feature_table["feature_id"] = None
        feature_data = {
            "library_name": [],
            "feature_id": [],
            "feature_kit_id": [],
        }
        for i, row in feature_table.iterrows():
            feature_kit_id = int(row["feature_kit_id"])
            feature_name = row["feature_name"]
            if pd.isna(feature_name):
                features, _ = db.get_features(feature_kit_id=feature_kit_id, limit=None)
                for feature in features:
                    feature_data["library_name"].append(row["library_name"])
                    feature_data["feature_kit_id"].append(feature_kit_id)
                    feature_data["feature_id"].append(feature.id)
            else:
                feature = db.get_feature_from_kit_by_feature_name(str(feature_name), feature_kit_id)
                if pd.isna(row["library_name"]):
                    abc_libraries = library_table[library_table["library_type_id"] == LibraryType.ANTIBODY_CAPTURE.id]["library_name"].unique().tolist()
                    for abc_library_name in abc_libraries:
                        feature_data["library_name"].append(abc_library_name)
                        feature_data["feature_kit_id"].append(feature_kit_id)
                        feature_data["feature_id"].append(feature.id)
                else:
                    feature_data["library_name"].append(row["library_name"])
                    feature_data["feature_kit_id"].append(feature_kit_id)
                    feature_data["feature_id"].append(feature.id)

        data["feature_table"] = pd.DataFrame(feature_data)

        self.update_data(data)
        return data
            
    def process_request(self, **context) -> Response:
        validated = self.validate()
        if not validated:
            return self.make_response(**context)

        data = self.__parse()
        library_table: pd.DataFrame = data["library_type"]  # type: ignore

        logger.debug(library_table)

        if (library_table["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id).any():
            visium_annotation_form = VisiumAnnotationForm(uuid=self.uuid)
            return visium_annotation_form.make_response(**context)

        if "pool" in library_table.columns:
            pool_mapping_form = PoolMappingForm(uuid=self.uuid)
            context = pool_mapping_form.prepare(data) | context
            return pool_mapping_form.make_response(**context)

        barcode_check_form = BarcodeCheckForm(uuid=self.uuid)
        context = barcode_check_form.prepare(data)
        return barcode_check_form.make_response(**context)