from typing import Optional
from flask import Response
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator

from opengsync_db import models
from opengsync_db.categories import LibraryType, FeatureType, KitType, MUXType

from .... import db, logger
from ...MultiStepForm import MultiStepForm
from ...SearchBar import SearchBar
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm


class FeatureMappingSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    feature_kit = FormField(SearchBar, label="Select Feature Kit")


class KitMappingForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-kit_mapping.html"
    _workflow_name = "library_annotation"
    _step_name = "kit_mapping"
    
    input_fields = FieldList(FormField(FeatureMappingSubForm), min_entries=1)

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        if "kit_table" not in current_step.tables:
            return False
        return current_step.tables["kit_table"]["kit_id"].isna().any()

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, workflow=KitMappingForm._workflow_name, step_name=KitMappingForm._step_name,
            uuid=uuid, formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

        self.kit_table = self.tables["kit_table"]
        self.feature_table = self.tables["feature_table"]
        
        if not formdata:
            for i, (_, row) in enumerate(self.kit_table.iterrows()):
                if pd.notna(row["kit_id"]):
                    continue
                
                if i > len(self.input_fields) - 1:
                    self.input_fields.append_entry()

                entry = self.input_fields[i]
                feature_kit_search_field: SearchBar = entry.feature_kit  # type: ignore
                entry.raw_label.data = row["name"] if pd.notna(row["name"]) else None

                if pd.isna(raw_kit_label := row["name"]):
                    selected_kit = None
                elif feature_kit_search_field.selected.data is None:
                    selected_kit = next(iter(db.kits.query(raw_kit_label, limit=1, kit_type=KitType.FEATURE_KIT)), None)
                    feature_kit_search_field.selected.data = selected_kit.id if selected_kit else None
                    feature_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None
                else:
                    selected_kit = db.feature_kits.get(feature_kit_search_field.selected.data)
                    feature_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None
    
    def validate(self) -> bool:
        validated = super().validate()
        if not validated:
            return False

        for i, (_, row) in enumerate(self.kit_table.iterrows()):
            if pd.notna(row["kit_id"]):
                continue
            
            raw_kit_label = row["name"]
            feature_kit_search_field: SearchBar = self.input_fields[i].feature_kit  # type: ignore

            if (kit_id := feature_kit_search_field.selected.data) is None:
                feature_kit_search_field.selected.errors = ("Not valid feature kit selected")
                return False
            
            if (_ := db.feature_kits.get(kit_id)) is None:
                logger.error(f"Feature kit with ID {kit_id} not found.")
                raise Exception()
            
            for _, row in self.feature_table[self.feature_table["kit"] == raw_kit_label].iterrows():
                if pd.isna(feature_name := row["feature"]):
                    continue
                
                if len(_ := db.features.get_from_kit_by_name(feature_name, kit_id)) == 0:
                    feature_kit_search_field.selected.errors = (f"Unknown feature '{feature_name}' does not belong to this feature kit.",)
                    return False

            self.kit_table.loc[self.kit_table["name"] == raw_kit_label, "kit_id"] = kit_id
        
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

        abc_libraries_df = library_table[(library_table["library_type_id"] == LibraryType.TENX_ANTIBODY_CAPTURE.id) | (library_table["library_type_id"] == LibraryType.TENX_SC_ABC_FLEX.id)]

        def add_feature(
            library_name: str, feature_name: str,
            sequence: str, pattern: str, read: str,
            kit_name: Optional[str] = None,
            kit_id: int | None = None,
            feature_id: int | None = None
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

            if (kit := db.feature_kits.get(kit_id)) is None:
                logger.error(f"Feature kit with ID {kit_id} not found.")
                raise Exception()
            
            if pd.isna(feature_name := row["feature"]):
                features, _ = db.features.find(feature_kit_id=kit_id, limit=None)
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
                for feature in db.features.get_from_kit_by_name(feature_name, kit_id):
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
    
    def get_sample_pooling_table(self, sample_pooling_table: pd.DataFrame) -> pd.DataFrame:
        mux_data = {
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

        def add_oligo(
            demux_name: str, sample_name: str,
            feature_name: str, sequence: str, pattern: str, read: str,
            kit_name: Optional[str] = None,
            kit_id: int | None = None,
            feature_id: int | None = None
        ):
            mux_data["demux_name"].append(demux_name)
            mux_data["sample_name"].append(sample_name)
            mux_data["kit"].append(kit_name)
            mux_data["kit_id"].append(kit_id)
            mux_data["feature"].append(feature_name)
            mux_data["sequence"].append(sequence)
            mux_data["pattern"].append(pattern)
            mux_data["read"].append(read)
            mux_data["feature_id"].append(feature_id)

        for i, row in sample_pooling_table.iterrows():
            if pd.isna(kit_id := row["kit_id"]):
                add_oligo(
                    demux_name=row["demux_name"],
                    sample_name=row["sample_name"],
                    feature_name=row["feature"],
                    sequence=row["sequence"],
                    pattern=row["pattern"],
                    read=row["read"],
                )
            else:
                if (kit := db.feature_kits.get(int(kit_id))) is None:
                    logger.error(f"Feature kit with ID {kit_id} not found.")
                    raise Exception(f"Feature kit with ID {kit_id} not found.")
                
                for feature in db.features.get_from_kit_by_name(row["feature"], kit_id):
                    add_oligo(
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

        return pd.DataFrame(mux_data)
    
    def process_request(self) -> Response:
        validated = self.validate()
        if not validated:
            return self.make_response()
        
        library_table = self.tables["library_table"]
        sample_pooling_table = self.tables["sample_pooling_table"]
        feature_table = self.tables.get("feature_table")

        for _, row in self.kit_table.iterrows():
            if row["type_id"] == FeatureType.CMO.id:
                if sample_pooling_table is None:
                    logger.error("MUX table should not be None")
                    raise Exception("MUX table should not be None")
                sample_pooling_table.loc[sample_pooling_table["kit"] == row["kit"], "kit_id"] = row["kit_id"]
            elif row["type_id"] == FeatureType.ANTIBODY.id:
                if feature_table is None:
                    logger.error("Feature table should not be None")
                    raise Exception("Feature table should not be None")
                feature_table.loc[feature_table["kit"] == row["name"], "kit_id"] = row["kit_id"]

        if (
            "kit" in sample_pooling_table.columns and
            (sample_pooling_table["mux_type_id"] == MUXType.TENX_OLIGO.id).any() and
            sample_pooling_table["kit"].notna().any()
        ):
            kit_mapping = self.kit_table.set_index("kit_name")["kit_id"].to_dict()
            sample_pooling_table.loc[sample_pooling_table["kit"].notna(), "kit_id"] = sample_pooling_table.loc[sample_pooling_table["kit"].notna(), "kit"].map(kit_mapping)
            sample_pooling_table = self.get_sample_pooling_table(sample_pooling_table)
            self.update_table("sample_pooling_table", sample_pooling_table, False)

        if feature_table is not None:
            feature_table = self.get_features(library_table, feature_table)
            self.update_table("feature_table", feature_table, False)
        
        self.add_table("kit_table", self.kit_table)
        self.update_data()

        if OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            
        return next_form.make_response()