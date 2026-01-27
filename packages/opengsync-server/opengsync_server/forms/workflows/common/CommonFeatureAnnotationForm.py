from typing import Optional

import pandas as pd

from flask import url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType, FeatureType
from opengsync_server.forms.MultiStepForm import StepFile

from .... import logger, tools, db  # noqa F401
from ....tools.spread_sheet_components import DropdownColumn, TextColumn, CategoricalDropDown, DuplicateCellValue, InvalidCellValue, MissingCellValue
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput, SpreadSheetColumn


class CommonFeatureAnnotationForm(MultiStepForm):
    _workflow_name: str
    _step_name = "feature_annotation"
    feature_table: pd.DataFrame

    @staticmethod
    def is_applicable(previous_form: MultiStepForm) -> bool:
        return bool(previous_form.tables["library_table"]["library_type_id"].isin(
            [LibraryType.TENX_ANTIBODY_CAPTURE.id, LibraryType.TENX_SC_ABC_FLEX.id]
        ).any())

    def __init__(
        self,
        workflow: str,
        lab_prep: models.LabPrep | None,
        seq_request: models.SeqRequest | None,
        additional_columns: list[SpreadSheetColumn],
        formdata: dict | None = None,
        uuid: Optional[str] = None,
    ):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=workflow,
            step_name=CommonFeatureAnnotationForm._step_name, step_args={}
        )
        self.seq_request = seq_request
        self.lab_prep = lab_prep

        self.kits_mapping = {kit.identifier: f"[{kit.identifier}] {kit.name}" for kit in db.feature_kits.find(limit=None, sort_by="name", type=FeatureType.ANTIBODY)[0]}

        self.library_table = self.tables["library_table"]
        self.abc_libraries = self.library_table[
            self.library_table["library_type_id"].isin(
                [LibraryType.TENX_ANTIBODY_CAPTURE.id, LibraryType.TENX_SC_ABC_FLEX.id]
            )
        ]
        self.abc_samples = self.abc_libraries["sample_name"].tolist()

        columns = [
            DropdownColumn("sample_name", "Sample Name", 170, choices=self.abc_samples, required=False),
            CategoricalDropDown("kit", "Kit", 250, categories=self.kits_mapping, required=False),
            TextColumn("identifier", "Identifier", 150, max_length=models.Feature.identifier.type.length, required=False, clean_up_fnc=tools.utils.normalize_to_ascii, validation_fnc=tools.utils.check_string),
            TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length),
            TextColumn("sequence", "Sequence", 150, max_length=models.Feature.sequence.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
            TextColumn("pattern", "Pattern", 200, max_length=models.Feature.pattern.type.length),
            DropdownColumn("read", "Read", 100, choices=["R2", "R1"]),
        ]

        self.columns = columns + additional_columns

        self.url_context = {}

        if self.seq_request is not None:
            self.url_context["seq_request_id"] = self.seq_request.id
            self._context["seq_request"] = self.seq_request
        if self.lab_prep is not None:
            self.url_context["lab_prep_id"] = self.lab_prep.id
            self._context["lab_prep"] = self.lab_prep

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=self._csrf_token,
            post_url=url_for(f"{workflow}_workflow.parse_feature_annotation", uuid=self.uuid, **self.url_context),
            formdata=formdata, allow_new_rows=True
        )

    def fill_previous_form(self, previous_form: StepFile):
        feature_table = previous_form.tables["feature_table"]
        self.spreadsheet.set_data(feature_table)

    def validate(self) -> bool:
        if not super().validate():
            return False
            
        if not self.spreadsheet.validate():
            return False
    
        self.df = self.spreadsheet.df

        # If ABC library is not mentioned in the feature table, i.e. no features assigned to it
        mentioned_abc_libraries = self.abc_libraries["sample_name"].isin(self.df["sample_name"])
        if pd.notna(self.df["sample_name"]).any() and not mentioned_abc_libraries.all():
            unmentioned = self.abc_libraries[~mentioned_abc_libraries]["sample_name"].values.tolist()
            self.spreadsheet.add_general_error(f"No features assigned to samples: {unmentioned}")
            return False
        
        kit_feature = pd.notna(self.df["kit"])
        custom_feature = pd.notna(self.df["feature"]) & pd.notna(self.df["sequence"]) & pd.notna(self.df["pattern"]) & pd.notna(self.df["read"])
        duplicate_identifier = pd.notna(self.df["identifier"]) & self.df.duplicated(subset=["identifier", "sample_name"], keep=False)
        duplicate_name = pd.notna(self.df["feature"]) & self.df.duplicated(subset=["feature", "sample_name"], keep=False)
        duplicated = self.df.duplicated(keep=False)

        kit_identifiers = self.df["kit"].dropna().unique().tolist()
        self.kits: dict[str, tuple[models.FeatureKit, pd.DataFrame]] = dict()
        
        self.df["kit_id"] = None
        for identifier in kit_identifiers:
            kit = db.feature_kits[identifier]
            kit_df = db.pd.get_feature_kit_features(kit.id)
            self.kits[identifier] = (kit, kit_df)
            self.df.loc[self.df["kit"] == identifier, "kit_id"] = kit.id

        for identifier, (kit, kit_df) in self.kits.items():
            view = self.df[self.df["kit"] == identifier]
            mask = kit_df["name"].isin(view["feature"])

            for _, kit_row in kit_df[mask].iterrows():
                self.df.loc[
                    (self.df["kit"] == identifier) & (self.df["feature"] == kit_row["name"]),
                    ["sequence", "pattern", "read"]
                ] = kit_row[["sequence", "pattern", "read"]].values

                self.df.loc[
                    (self.df["kit"] == identifier) & (self.df["identifier"] == kit_row["identifier"]),
                    ["sequence", "pattern", "read"]
                ] = kit_row[["sequence", "pattern", "read"]].values

        for idx, row in self.df.iterrows():
            if duplicate_identifier.at[idx]:
                self.spreadsheet.add_error(idx, "identifier", DuplicateCellValue("duplicate feature definition"))

            if duplicate_name.at[idx]:
                self.spreadsheet.add_error(idx, "feature", DuplicateCellValue("duplicate feature name"))

            if duplicated.at[idx]:
                self.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "kit", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "feature", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "read", DuplicateCellValue("duplicate feature definition"))

            if pd.notna(row["sample_name"]) and row["sample_name"] not in self.abc_libraries["sample_name"].values:
                self.spreadsheet.add_error(idx, "sample_name", InvalidCellValue(f"'Sample Name' must be one of: [{', '.join(set(self.abc_libraries['sample_name'].values.tolist()))}]"))

            if kit_feature.at[idx]:
                identifier = row["kit"]
                kit, kit_df = self.kits[identifier]
                if pd.notna(row["identifier"]):
                    if row["identifier"] not in kit_df["identifier"].values:
                        self.spreadsheet.add_error(idx, "identifier", InvalidCellValue(f"Identifier '{row['identifier']}' not found in kit '{identifier}'"))
                        continue
                if pd.notna(row["feature"]):
                    if row["feature"] not in kit_df["name"].values:
                        self.spreadsheet.add_error(idx, "feature", InvalidCellValue(f"Feature '{row['feature']}' not found in kit '{identifier}'"))
                        continue

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
                idx_sample_name = self.df["sample_name"] == row["sample_name"]
                idx_sequence = self.df["sequence"] == row["sequence"]
                idx_pattern = self.df["pattern"] == row["pattern"]
                idx_read = self.df["read"] == row["read"]

                idx = idx_sequence & idx_pattern & idx_read
                if pd.notna(row["sample_name"]):
                    idx = idx & idx_sample_name

                if self.df[idx].shape[0] > 1:
                    self.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination in same library."))
                    self.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination in same library."))
                    self.spreadsheet.add_error(idx, "read", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination in same library."))

            elif kit_feature.at[idx]:
                idx_sample_name = self.df["sample_name"] == row["sample_name"]
                idx_kit = self.df["kit"] == row["kit"]
                idx_feature = self.df["feature"] == row["feature"]
                idx = True
                if pd.notna(row["sample_name"]):
                    idx = idx & idx_sample_name
                if pd.notna(row["kit"]):
                    idx = idx & idx_kit
                if pd.notna(row["feature"]):
                    idx = idx & idx_feature
                
                if self.df[idx].shape[0] > 1:
                    self.spreadsheet.add_error(idx, "feature", DuplicateCellValue("Duplicate 'Kit' + 'Feature' specified for same library."))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = self.df
        library_sample_map = self.abc_libraries.set_index("sample_name").to_dict()["library_name"]
        self.df["library_name"] = self.df["sample_name"].map(library_sample_map)
        return True
    
    def get_feature_table(self) -> pd.DataFrame:
        feature_data = {
            "library_name": [],
            "kit": [],
            "identifier": [],
            "feature": [],
            "sequence": [],
            "pattern": [],
            "read": [],
            "kit_id": [],
            "feature_id": [],
        }

        def add_feature(
            library_name: str | None, feature_name: str,
            sequence: str, pattern: str, read: str,
            identifier: str | None,
            kit_name: Optional[str] = None,
            kit_id: int | None = None,
            feature_id: int | None = None
        ):
            feature_data["library_name"].append(library_name)
            feature_data["kit_id"].append(kit_id)
            feature_data["feature_id"].append(feature_id)
            feature_data["identifier"].append(identifier)
            feature_data["kit"].append(kit_name)
            feature_data["feature"].append(feature_name)
            feature_data["sequence"].append(sequence)
            feature_data["pattern"].append(pattern)
            feature_data["read"].append(read)

        for _, row in self.df.iterrows():
            if pd.isna(kit_identifier := row["kit"]):
                add_feature(
                    library_name=row["library_name"],
                    feature_name=row["feature"],
                    identifier=row["identifier"],
                    sequence=row["sequence"],
                    pattern=row["pattern"],
                    read=row["read"],
                )
                continue

            kit, kit_df = self.kits[kit_identifier]

            if pd.isna(row["identifier"]) and pd.isna(row["feature"]):
                for _, kit_row in kit_df.iterrows():
                    add_feature(
                        library_name=row["library_name"],
                        kit_id=kit.id,
                        kit_name=row["kit"],
                        identifier=kit_row["identifier"],
                        feature_id=kit_row["feature_id"],
                        feature_name=kit_row["name"],
                        sequence=kit_row["sequence"],
                        pattern=kit_row["pattern"],
                        read=kit_row["read"]
                    )
            elif pd.notna(row["identifier"]):
                for _, kit_row in kit_df[kit_df["identifier"] == row["identifier"]].iterrows():
                    add_feature(
                        library_name=row["library_name"],
                        kit_id=kit.id,
                        kit_name=row["kit"],
                        identifier=kit_row["identifier"],
                        feature_id=kit_row["feature_id"],
                        feature_name=kit_row["name"],
                        sequence=kit_row["sequence"],
                        pattern=kit_row["pattern"],
                        read=kit_row["read"]
                    )
            elif pd.notna(row["feature"]):
                for _, kit_row in kit_df[kit_df["name"] == row["feature"]].iterrows():
                    add_feature(
                        library_name=row["library_name"],
                        kit_id=kit.id,
                        kit_name=row["kit"],
                        identifier=kit_row["identifier"],
                        feature_id=kit_row["feature_id"],
                        feature_name=kit_row["name"],
                        sequence=kit_row["sequence"],
                        pattern=kit_row["pattern"],
                        read=kit_row["read"]
                    )

        return pd.DataFrame(feature_data)
