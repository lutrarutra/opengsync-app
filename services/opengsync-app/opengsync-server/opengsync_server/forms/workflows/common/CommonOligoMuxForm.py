import pandas as pd

from flask import url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType, FeatureType

from .... import logger, tools, db  # noqa F401
from ....tools import utils
from ...MultiStepForm import MultiStepForm, StepFile
from ...SpreadsheetInput import SpreadsheetInput, SpreadSheetColumn
from ....tools.spread_sheet_components import TextColumn, InvalidCellValue, MissingCellValue, CategoricalDropDown, DropdownColumn, DuplicateCellValue


class CommonOligoMuxForm(MultiStepForm):
    _step_name = "oligo_mux_annotation"
    spreadsheet: SpreadsheetInput
    library_table: pd.DataFrame
    df: pd.DataFrame
    index_col: str

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return bool(current_step.tables["library_table"]["library_type_id"].isin([LibraryType.TENX_MUX_OLIGO.id]).any())
    
    @classmethod
    def __get_multiplexed_samples(cls, df: pd.DataFrame) -> list[str]:
        multiplexed_samples = set()
        for sample_name, _df in df.groupby("sample_name"):
            if LibraryType.TENX_MUX_OLIGO.id in _df["library_type_id"].unique():
                multiplexed_samples.add(sample_name)
        return list(multiplexed_samples)

    def __init__(
        self,
        workflow: str,
        seq_request: models.SeqRequest | None,
        lab_prep: models.LabPrep | None,
        formdata: dict | None,
        uuid: str | None,
        additional_columns: list[SpreadSheetColumn],
    ):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=workflow,
            step_name=CommonOligoMuxForm._step_name, step_args={}
        )

        self.seq_request = seq_request
        self.lab_prep = lab_prep

        self.kits_mapping = {kit.identifier: f"[{kit.identifier}] {kit.name}" for kit in db.feature_kits.find(limit=None, sort_by="name", type=FeatureType.CMO)[0]}

        self.multiplexed_samples = CommonOligoMuxForm.__get_multiplexed_samples(self.tables["library_table"])
        
        columns = [
            TextColumn("demux_name", "Demultiplexed Name", 170, required=True, max_length=models.Sample.name.type.length, min_length=4, validation_fnc=utils.check_string),
            DropdownColumn("sample_name", "Sample (Pool) Name", 170, choices=self.multiplexed_samples, required=True),
            CategoricalDropDown("kit", "Kit", 250, categories=self.kits_mapping, required=False),
            TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length, min_length=4, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
            TextColumn("sequence", "Sequence", 150, max_length=models.Feature.sequence.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
            TextColumn("pattern", "Pattern", 200, max_length=models.Feature.pattern.type.length, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
            DropdownColumn("read", "Read", 100, choices=["R2", "R1"]),
        ]

        self.columns = additional_columns + columns

        self.url_context = {}
        if self.seq_request is not None:
            self._context["seq_request"] = self.seq_request
            self.url_context["seq_request_id"] = self.seq_request.id
        if self.lab_prep is not None:
            self._context["lab_prep"] = self.lab_prep
            self.url_context["lab_prep_id"] = self.lab_prep.id

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=self._csrf_token,
            post_url=url_for(f"{workflow}_workflow.parse_oligo_mux_reference", uuid=self.uuid, **self.url_context),
            formdata=formdata, allow_new_rows=True
        )

    def fill_previous_form(self, previous_form: StepFile):
        df = previous_form.tables["sample_pooling_table"]
        df = df.drop_duplicates(subset=["sample_name"]).rename(columns={
            "sample_name": "demux_name",
            "sample_pool": "sample_name",
        })
        self.spreadsheet.set_data(df)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        self.df = self.spreadsheet.df

        kit_feature = pd.notna(self.df["kit"]) & pd.notna(self.df["feature"])
        custom_feature = pd.notna(self.df["sequence"]) & pd.notna(self.df["pattern"]) & pd.notna(self.df["read"])
        invalid_feature = (pd.notna(self.df["kit"]) | pd.notna(self.df["feature"])) & (pd.notna(self.df["sequence"]) | pd.notna(self.df["pattern"]) | pd.notna(self.df["read"]))
        
        kit_identifiers = self.df["kit"].dropna().unique().tolist()
        kits: dict[str, tuple[models.FeatureKit, pd.DataFrame]] = dict()
        
        self.df["kit_id"] = None
        for identifier in kit_identifiers:
            kit = db.feature_kits[identifier]
            kit_df = db.pd.get_feature_kit_features(kit.id)
            kits[identifier] = (kit, kit_df)
            self.df.loc[self.df["kit"] == identifier, "kit_id"] = kit.id

        duplicate_oligo = (
            (self.df.duplicated(subset=["sample_name", "sequence", "pattern", "read"], keep=False) & custom_feature) |
            (self.df.duplicated(subset=["sample_name", "kit", "feature"], keep=False) & kit_feature)
        )

        for identifier, (kit, kit_df) in kits.items():
            view = self.df[self.df["kit"] == identifier]
            mask = kit_df["name"].isin(view["feature"])

            for _, kit_row in kit_df[mask].iterrows():
                self.df.loc[
                    (self.df["kit"] == identifier) & (self.df["feature"] == kit_row["name"]),
                    ["sequence", "pattern", "read"]
                ] = kit_row[["sequence", "pattern", "read"]].values
                
        for idx, row in self.df.iterrows():
            # Not defined custom nor kit feature
            if kit_feature.at[idx]:
                identifier = row["kit"]
                kit, kit_df = kits[identifier]
                if pd.notna(row["feature"]):
                    if row["feature"] not in kit_df["name"].values:
                        self.spreadsheet.add_error(idx, "feature", InvalidCellValue(f"Feature '{row['feature']}' not found in kit '{identifier}'"))
                        continue
            
            if (not custom_feature.at[idx] and not kit_feature.at[idx]):
                self.spreadsheet.add_error(idx, "kit", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "feature", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "sequence", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "pattern", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "read", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))

            # Defined both custom and kit feature
            elif custom_feature.at[idx] and kit_feature.at[idx]:
                self.spreadsheet.add_error(idx, "kit", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "feature", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "sequence", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "pattern", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "read", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))

            elif invalid_feature.at[idx]:
                if pd.notna(row["kit"]):
                    self.spreadsheet.add_error(idx, "kit", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                if pd.notna(row["feature"]):
                    self.spreadsheet.add_error(idx, "feature", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                if pd.notna(row["sequence"]):
                    self.spreadsheet.add_error(idx, "sequence", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                if pd.notna(row["pattern"]):
                    self.spreadsheet.add_error(idx, "pattern", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                if pd.notna(row["read"]):
                    self.spreadsheet.add_error(idx, "read", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))

            if duplicate_oligo.at[idx]:
                self.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("Definitions must be unique for each sample."))
                self.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("Definitions must be unique for each sample."))
                self.spreadsheet.add_error(idx, "read", DuplicateCellValue("Definitions must be unique for each sample."))
                self.spreadsheet.add_error(idx, "kit", DuplicateCellValue("Definitions must be unique for each sample."))
                self.spreadsheet.add_error(idx, "feature", DuplicateCellValue("Definitions must be unique for each sample."))

        logger.debug(self.kits_mapping)
        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df["custom_feature"] = custom_feature
        self.df["kit_feature"] = kit_feature

        return True
