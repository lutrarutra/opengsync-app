from typing import Optional

import pandas as pd

from flask import Response, url_for

from limbless_db import models
from limbless_db.categories import LibraryType, FeatureType

from .... import db, logger, tools  # noqa
from ....tools import SpreadSheetColumn
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput
from .KitMappingForm import KitMappingForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FRPAnnotationForm import FRPAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm


class FeatureAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-feature_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "feature_annotation"

    columns = {
        "library_name": SpreadSheetColumn("A", "library_name", "Library Name", "text", 170, str),
        "kit": SpreadSheetColumn("B", "kit", "Kit", "text", 170, str),
        "feature": SpreadSheetColumn("C", "feature", "Feature", "text", 150, str),
        "sequence": SpreadSheetColumn("D", "sequence", "Sequence", "text", 150, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        "pattern": SpreadSheetColumn("E", "pattern", "Pattern", "text", 200, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
        "read": SpreadSheetColumn("F", "read", "Read", "text", 100, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    }

    def __init__(self, seq_request: models.SeqRequest, uuid: str, previous_form: Optional[MultiStepForm] = None, formdata: dict = {}):
        MultiStepForm.__init__(
            self, workflow=FeatureAnnotationForm._workflow_name,
            step_name=FeatureAnnotationForm._step_name, uuid=uuid,
            formdata=formdata, previous_form=previous_form, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=FeatureAnnotationForm.columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.annotate_features', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )

    def validate(self) -> bool:
        if not super().validate():
            return False
            
        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df

        library_table = self.tables["library_table"]
        abc_libraries = library_table[library_table["library_type_id"] == LibraryType.TENX_ANTIBODY_CAPTURE.id]
            
        # If ABC library is not mentioned in the feature table, i.e. no features assigned to it
        mentioned_abc_libraries = abc_libraries["library_name"].isin(df["library_name"])
        if pd.notna(df["library_name"]).any() and not mentioned_abc_libraries.all():
            unmentioned = abc_libraries[~mentioned_abc_libraries]["library_name"].values.tolist()
            self.spreadsheet.add_general_error(f"No features assigned to libraries: {unmentioned}")
            return False
        
        kit_feature = pd.notna(df["kit"])
        custom_feature = pd.notna(df["feature"]) & pd.notna(df["sequence"]) & pd.notna(df["pattern"]) & pd.notna(df["read"])
        invalid_feature = pd.notna(df["kit"]) & (pd.notna(df["sequence"]) | pd.notna(df["pattern"]) | pd.notna(df["read"]))
        duplicated = df.duplicated(keep=False)

        for i, (idx, row) in enumerate(df.iterrows()):
            if duplicated.at[idx]:
                self.spreadsheet.add_error(i + 1, "library_name", "duplicate feature definition", "duplicate_value")
                self.spreadsheet.add_error(i + 1, "kit", "duplicate feature definition", "duplicate_value")
                self.spreadsheet.add_error(i + 1, "feature", "duplicate feature definition", "duplicate_value")
                self.spreadsheet.add_error(i + 1, "sequence", "duplicate feature definition", "duplicate_value")
                self.spreadsheet.add_error(i + 1, "pattern", "duplicate feature definition", "duplicate_value")
                self.spreadsheet.add_error(i + 1, "read", "duplicate feature definition", "duplicate_value")

            if pd.notna(row["library_name"]) and row["library_name"] not in abc_libraries["library_name"].values:
                self.spreadsheet.add_error(i + 1, "library_name", f"'Library Name' must be one of: [{', '.join(set(abc_libraries['library_name'].values.tolist()))}]", "invalid_value")

            # Defined both kit and custom
            if invalid_feature.at[idx]:
                if pd.notna(row["kit"]):
                    self.spreadsheet.add_error(i + 1, "kit", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "invalid_input")
                if pd.notna(row["sequence"]):
                    self.spreadsheet.add_error(i + 1, "sequence", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "invalid_input")
                if pd.notna(row["pattern"]):
                    self.spreadsheet.add_error(i + 1, "pattern", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "invalid_input")
                if pd.notna(row["read"]):
                    self.spreadsheet.add_error(i + 1, "read", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "invalid_input")
            # Not defined custom nor kit feature
            elif (not custom_feature.at[idx] and not kit_feature.at[idx]):
                self.spreadsheet.add_error(i + 1, "kit", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "missing_value")
                self.spreadsheet.add_error(i + 1, "feature", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "missing_value")
                self.spreadsheet.add_error(i + 1, "sequence", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "missing_value")
                self.spreadsheet.add_error(i + 1, "pattern", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "missing_value")
                self.spreadsheet.add_error(i + 1, "read", "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.", "missing_value")

            # Defined both custom and kit feature
            elif custom_feature.at[idx] and kit_feature.at[idx]:
                self.spreadsheet.add_error(i + 1, "kit", "must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")
                self.spreadsheet.add_error(i + 1, "feature", "must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")
                self.spreadsheet.add_error(i + 1, "sequence", "must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")
                self.spreadsheet.add_error(i + 1, "pattern", "must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")
                self.spreadsheet.add_error(i + 1, "read", "must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both.", "invalid_input")

            elif custom_feature.at[idx]:
                idx_library_name = df["library_name"] == row["library_name"]
                idx_sequence = df["sequence"] == row["sequence"]
                idx_pattern = df["pattern"] == row["pattern"]
                idx_read = df["read"] == row["read"]

                idx = idx_sequence & idx_pattern & idx_read
                if pd.notna(row["library_name"]):
                    idx = idx & idx_library_name

                if df[idx].shape[0] > 1:
                    self.spreadsheet.add_error(i + 1, "sequence", f"Row {i+1} has duplicate 'Sequence + Pattern + Read' combination in same library.", "duplicate_value")
                    self.spreadsheet.add_error(i + 1, "pattern", f"Row {i+1} has duplicate 'Sequence + Pattern + Read' combination in same library.", "duplicate_value")
                    self.spreadsheet.add_error(i + 1, "read", f"Row {i+1} has duplicate 'Sequence + Pattern + Read' combination in same library.", "duplicate_value")

            elif kit_feature.at[idx]:
                idx_library_name = df["library_name"] == row["library_name"]
                idx_kit = df["kit"] == row["kit"]
                idx_feature = df["feature"] == row["feature"]
                idx = True
                if pd.notna(row["library_name"]):
                    idx = idx & idx_library_name
                if pd.notna(row["kit"]):
                    idx = idx & idx_kit
                if pd.notna(row["feature"]):
                    idx = idx & idx_feature
                
                if df[idx].shape[0] > 1:
                    self.spreadsheet.add_error(i + 1, "feature", f"Row {i+1} has duplicate 'Kit' + 'Feature' specified for same library.", "duplicate_value")

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.feature_table = df
        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        library_table = self.tables["library_table"]

        feature_data = {
            "library_name": [],
            "kit": [],
            "kit_id": [],
            "feature": [],
            "sequence": [],
            "pattern": [],
            "read": [],
            "feature_id": [],
        }
        abc_libraries_df = library_table[library_table["library_type_id"] == LibraryType.TENX_ANTIBODY_CAPTURE.id]

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

        if (kit_table := self.tables.get("kit_table")) is None:  # type: ignore
            kit_table = self.feature_table.loc[self.feature_table["kit"].notna(), ["kit", "kit_id"]].drop_duplicates().copy().rename(columns={"kit": "name"})
            kit_table["type_id"] = FeatureType.ANTIBODY.id
            self.add_table("kit_table", kit_table)
        else:
            _kit_table = self.feature_table.loc[self.feature_table["kit"].notna(), ["kit", "kit_id"]].drop_duplicates().copy().rename(columns={"kit": "name"})
            _kit_table["type_id"] = FeatureType.ANTIBODY.id
            kit_table = pd.concat([kit_table, _kit_table])
            self.update_table("kit_table", kit_table, False)

        self.add_table("feature_table", self.feature_table)
        self.update_data()
        
        if kit_table["kit_id"].isna().any():
            feature_kit_mapping_form = KitMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            feature_kit_mapping_form.prepare()
            return feature_kit_mapping_form.make_response()
        
        if (library_table["library_type_id"].isin([LibraryType.TENX_VISIUM.id, LibraryType.TENX_VISIUM_FFPE.id, LibraryType.TENX_VISIUM_HD.id])).any():
            visium_annotation_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            visium_annotation_form.prepare()
            return visium_annotation_form.make_response()
        
        if self.metadata["workflow_type"] == "pooled" and LibraryType.TENX_SC_GEX_FLEX.id in library_table["library_type_id"].values:
            frp_annotation_form = FRPAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return frp_annotation_form.make_response()

        sample_annotation_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return sample_annotation_form.make_response()
        
