from typing import Optional

import pandas as pd

from flask import Response, url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType, FeatureType

from .... import db, logger, tools  # noqa
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput
from ....tools.spread_sheet_components import TextColumn, DropdownColumn, InvalidCellValue, MissingCellValue, DuplicateCellValue
from .KitMappingForm import KitMappingForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm


class FeatureAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-feature_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "feature_annotation"

    columns = [
        DropdownColumn("sample_name", "Sample Name", 170, choices=[], required=False),
        TextColumn("kit", "Kit", 170, max_length=64),
        TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length),
        TextColumn("sequence", "Sequence", 150, max_length=models.Feature.sequence.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        TextColumn("pattern", "Pattern", 200, max_length=models.Feature.pattern.type.length),
        DropdownColumn("read", "Read", 100, choices=["", "R2", "R1"]),
    ]

    @staticmethod
    def is_applicable(previous_form: MultiStepForm) -> bool:
        return previous_form.tables["library_table"]["library_type_id"].isin([LibraryType.TENX_ANTIBODY_CAPTURE.id, LibraryType.TENX_SC_ABC_FLEX.id]).any()

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, workflow=FeatureAnnotationForm._workflow_name,
            step_name=FeatureAnnotationForm._step_name, uuid=uuid,
            formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=FeatureAnnotationForm.columns, csrf_token=self._csrf_token,
            post_url=url_for('library_annotation_workflow.annotate_features', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )

        self.library_table = self.tables["library_table"]
        self.abc_libraries = self.library_table[(self.library_table["library_type_id"] == LibraryType.TENX_ANTIBODY_CAPTURE.id) | (self.library_table["library_type_id"] == LibraryType.TENX_SC_ABC_FLEX.id)]
        self.abc_samples = self.abc_libraries["sample_name"].tolist()

        self.spreadsheet.columns["sample_name"].source = self.abc_samples

    def validate(self) -> bool:
        if not super().validate():
            return False
            
        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df

        # If ABC library is not mentioned in the feature table, i.e. no features assigned to it
        mentioned_abc_libraries = self.abc_libraries["sample_name"].isin(df["sample_name"])
        if pd.notna(df["sample_name"]).any() and not mentioned_abc_libraries.all():
            unmentioned = self.abc_libraries[~mentioned_abc_libraries]["sample_name"].values.tolist()
            self.spreadsheet.add_general_error(f"No features assigned to samples: {unmentioned}")
            return False
        
        kit_feature = pd.notna(df["kit"])
        custom_feature = pd.notna(df["feature"]) & pd.notna(df["sequence"]) & pd.notna(df["pattern"]) & pd.notna(df["read"])
        invalid_feature = pd.notna(df["kit"]) & (pd.notna(df["sequence"]) | pd.notna(df["pattern"]) | pd.notna(df["read"]))
        duplicated = df.duplicated(keep=False)

        for i, (idx, row) in enumerate(df.iterrows()):
            if duplicated.at[idx]:
                self.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "kit", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "feature", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "read", DuplicateCellValue("duplicate feature definition"))

            if pd.notna(row["sample_name"]) and row["sample_name"] not in self.abc_libraries["sample_name"].values:
                self.spreadsheet.add_error(idx, "sample_name", InvalidCellValue(f"'Sample Name' must be one of: [{', '.join(set(self.abc_libraries['sample_name'].values.tolist()))}]"))

            # Defined both kit and custom
            if invalid_feature.at[idx]:
                if pd.notna(row["kit"]):
                    self.spreadsheet.add_error(idx, "kit", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                if pd.notna(row["sequence"]):
                    self.spreadsheet.add_error(idx, "sequence", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                if pd.notna(row["pattern"]):
                    self.spreadsheet.add_error(idx, "pattern", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                if pd.notna(row["read"]):
                    self.spreadsheet.add_error(idx, "read", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
            # Not defined custom nor kit feature
            elif (not custom_feature.at[idx] and not kit_feature.at[idx]):
                self.spreadsheet.add_error(idx, "kit", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "feature", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "sequence", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "pattern", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "read", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))

            # Defined both custom and kit feature
            elif custom_feature.at[idx] and kit_feature.at[idx]:
                self.spreadsheet.add_error(idx, "kit", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "feature", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "sequence", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "pattern", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "read", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))

            elif custom_feature.at[idx]:
                idx_sample_name = df["sample_name"] == row["sample_name"]
                idx_sequence = df["sequence"] == row["sequence"]
                idx_pattern = df["pattern"] == row["pattern"]
                idx_read = df["read"] == row["read"]

                idx = idx_sequence & idx_pattern & idx_read
                if pd.notna(row["sample_name"]):
                    idx = idx & idx_sample_name

                if df[idx].shape[0] > 1:
                    self.spreadsheet.add_error(idx, "sequence", DuplicateCellValue(f"Row {i + 1} has duplicate 'Sequence + Pattern + Read' combination in same library."))
                    self.spreadsheet.add_error(idx, "pattern", DuplicateCellValue(f"Row {i + 1} has duplicate 'Sequence + Pattern + Read' combination in same library."))
                    self.spreadsheet.add_error(idx, "read", DuplicateCellValue(f"Row {i + 1} has duplicate 'Sequence + Pattern + Read' combination in same library."))

            elif kit_feature.at[idx]:
                idx_sample_name = df["sample_name"] == row["sample_name"]
                idx_kit = df["kit"] == row["kit"]
                idx_feature = df["feature"] == row["feature"]
                idx = True
                if pd.notna(row["sample_name"]):
                    idx = idx & idx_sample_name
                if pd.notna(row["kit"]):
                    idx = idx & idx_kit
                if pd.notna(row["feature"]):
                    idx = idx & idx_feature
                
                if df[idx].shape[0] > 1:
                    self.spreadsheet.add_error(idx, "feature", DuplicateCellValue(f"Row {i + 1} has duplicate 'Kit' + 'Feature' specified for same library."))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.feature_table = df
        library_sample_map = self.abc_libraries.set_index("sample_name").to_dict()["library_name"]
        self.feature_table["library_name"] = self.feature_table["sample_name"].map(library_sample_map)
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
        abc_libraries_df = library_table[(library_table["library_type_id"] == LibraryType.TENX_ANTIBODY_CAPTURE.id) | (library_table["library_type_id"] == LibraryType.TENX_SC_ABC_FLEX.id)]

        def add_feature(
            library_name: str, feature_name: str,
            sequence: str, pattern: str, read: str,
            kit_name: Optional[str],
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
            kit_table = pd.concat([kit_table[kit_table["type_id"] != FeatureType.ANTIBODY.id], _kit_table])
            self.update_table("kit_table", kit_table, False)

        self.add_table("feature_table", self.feature_table)
        self.update_data()

        if KitMappingForm.is_applicable(self):
            next_form = KitMappingForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        
        return next_form.make_response()
        
