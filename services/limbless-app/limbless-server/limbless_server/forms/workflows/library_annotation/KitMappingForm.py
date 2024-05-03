from typing import Optional
from flask import Response
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator

from limbless_db.categories import LibraryType, FeatureType

from .... import db, logger
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import SearchBar
from .PoolMappingForm import PoolMappingForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .CompleteSASForm import CompleteSASForm


class FeatureMappingSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    feature_kit = FormField(SearchBar, label="Select Feature Kit")


class KitMappingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-8.html"

    input_fields = FieldList(FormField(FeatureMappingSubForm), min_entries=1)

    def __init__(self, previous_form: Optional[TableDataForm] = None, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid, previous_form=previous_form)
    
    def prepare(self):
        kit_table = self.tables["kit_table"]

        for i, (_, row) in enumerate(kit_table.iterrows()):
            if pd.notna(row["kit_id"]):
                continue
            
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields[i]
            feature_kit_search_field: SearchBar = entry.feature_kit  # type: ignore
            entry.raw_label.data = raw_kit_label

            if pd.isna(raw_kit_label := row["name"]):
                selected_kit = None
            elif feature_kit_search_field.selected.data is None:
                selected_kit = next(iter(db.query_feature_kits(raw_kit_label, 1)), None)
                feature_kit_search_field.selected.data = selected_kit.id if selected_kit else None
                feature_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None
            else:
                selected_kit = db.get_feature_kit(feature_kit_search_field.selected.data)
                feature_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None
    
    def validate(self) -> bool:
        validated = super().validate()
        if not validated:
            return False
        
        kit_table = self.tables["kit_table"]

        for i, (_, row) in enumerate(kit_table.iterrows()):
            if pd.notna(row["kit_id"]):
                continue
            
            raw_kit_label = row["name"]
            feature_kit_search_field: SearchBar = self.input_fields[i].feature_kit  # type: ignore

            if (kit_id := feature_kit_search_field.selected.data) is None:
                feature_kit_search_field.selected.errors = ("Not valid feature kit selected")
                return False
            
            if (_ := db.get_feature_kit(kit_id)) is None:
                logger.error(f"Feature kit with ID {kit_id} not found.")
                raise Exception()
            
            for _, row in kit_table[kit_table["name"] == raw_kit_label].iterrows():
                if pd.isna(feature_name := row["feature"]):
                    continue
                
                if (_ := db.get_feature_from_kit_by_feature_name(feature_name, kit_id)) is None:
                    feature_kit_search_field.selected.errors = (f"Unknown feature '{feature_name}' does not belong to this feature kit.",)
                    return False

            kit_table.loc[kit_table["name"] == kit_table, "kit_id"] = kit_id

        self.kit_table = kit_table

        return validated
    
    def get_features(self, library_table: pd.DataFrame, feature_table: pd.DataFrame) -> pd.DataFrame:
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
            kit_name: Optional[str] = None,
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

        for i, row in feature_table.iterrows():
            if pd.isna(kit_id := row["kit_id"]):
                add_feature(
                    library_name=row["library_name"],
                    feature_name=row["feature"],
                    sequence=row["sequence"],
                    pattern=row["pattern"],
                    read=row["read"],
                )
                continue

            if (kit := db.get_feature_kit(kit_id)) is None:
                logger.error(f"Feature kit with ID {kit_id} not found.")
                raise Exception()
            
            if pd.isna(feature_name := row["feature"]):
                features, _ = db.get_features(feature_kit_id=kit_id, limit=None)
                for feature in features:
                    if pd.isna(library_name := row["library_name"]):
                        for library_name in abc_libraries_df["library_name"]:
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
                    else:
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
            else:
                feature = db.get_feature_from_kit_by_feature_name(feature_name, kit_id)
                if pd.isna(row["library_name"]):
                    for library_name in abc_libraries_df["library_name"]:
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
                else:
                    add_feature(
                        library_name=row["library_name"],
                        kit_id=kit.id,
                        kit_name=kit.name,
                        feature_id=feature.id,
                        feature_name=feature.name,
                        sequence=feature.sequence,
                        pattern=feature.pattern,
                        read=feature.read
                    )
        return pd.DataFrame(feature_data)
    
    def get_cmos(self, cmo_table: pd.DataFrame) -> pd.DataFrame:
        cmo_data = {
            "demux_name": [],
            "sample_name": [],
            "kit": [],
            "kit_id": [],
            "feature": [],
            "sequence": [],
            "pattern": [],
            "read": [],
            "feature_id": [],
        }

        def add_cmo(
            demux_name: str, sample_name: str,
            feature_name: str, sequence: str, pattern: str, read: str,
            kit_name: Optional[str] = None,
            kit_id: Optional[int] = None,
            feature_id: Optional[int] = None
        ):
            cmo_data["demux_name"].append(demux_name)
            cmo_data["sample_name"].append(sample_name)
            cmo_data["kit"].append(kit_name)
            cmo_data["kit_id"].append(kit_id)
            cmo_data["feature"].append(feature_name)
            cmo_data["sequence"].append(sequence)
            cmo_data["pattern"].append(pattern)
            cmo_data["read"].append(read)
            cmo_data["feature_id"].append(feature_id)

        for i, row in cmo_table.iterrows():
            # Custom CMO
            if pd.isna(kit_id := row["kit_id"]):
                add_cmo(
                    demux_name=row["demux_name"],
                    sample_name=row["sample_name"],
                    feature_name=row["feature"],
                    sequence=row["sequence"],
                    pattern=row["pattern"],
                    read=row["read"],
                )
            else:
                if (kit := db.get_feature_kit(int(kit_id))) is None:
                    logger.error(f"Feature kit with ID {kit_id} not found.")
                    raise Exception(f"Feature kit with ID {kit_id} not found.")
                
                feature = db.get_feature_from_kit_by_feature_name(row["feature"], kit_id)
                add_cmo(
                    demux_name=row["demux_name"],
                    sample_name=row["sample_name"],
                    kit_id=kit.id,
                    kit_name=kit.name,
                    feature_id=feature.id,
                    feature_name=feature.name,
                    sequence=feature.sequence,
                    pattern=feature.pattern,
                    read=feature.read
                )

        return pd.DataFrame(cmo_data)
    
    def process_request(self, **context) -> Response:
        validated = self.validate()
        if not validated:
            return self.make_response(**context)
        
        library_table = self.tables["library_table"]
        cmo_table = self.tables.get("cmo_table")
        feature_table = self.tables.get("feature_table")

        for _, row in self.kit_table.iterrows():
            if row["kit_type_id"] == FeatureType.CMO.id:
                if cmo_table is None:
                    logger.error("CMO table should not be None")
                    raise Exception("CMO table should not be None")
                cmo_table.loc[cmo_table["kit"] == row["kit"], "kit_id"] = row["kit_id"]
            elif row["kit_type_id"] == FeatureType.ANTIBODY.id:
                if feature_table is None:
                    logger.error("Feature table should not be None")
                    raise Exception("Feature table should not be None")
                feature_table.loc[feature_table["kit"] == row["kit"], "kit_id"] = row["kit_id"]

        if cmo_table is not None:
            cmo_table = self.get_cmos(cmo_table)
            self.update_table("cmo_table", cmo_table, False)

        if feature_table is not None:
            feature_table = self.get_features(library_table, feature_table)
            self.update_table("feature_table", feature_table, False)
        
        self.add_table("kit_table", self.kit_table)
        self.update_data()

        if (library_table["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id).any():
            visium_annotation_form = VisiumAnnotationForm(previous_form=self, uuid=self.uuid)
            visium_annotation_form.prepare()
            return visium_annotation_form.make_response(**context)

        if "pool" in library_table.columns:
            pool_mapping_form = PoolMappingForm(previous_form=self, uuid=self.uuid)
            pool_mapping_form.prepare()
            return pool_mapping_form.make_response(**context)

        complete_sas_form = CompleteSASForm(previous_form=self, uuid=self.uuid)
        complete_sas_form.prepare()
        return complete_sas_form.make_response(**context)