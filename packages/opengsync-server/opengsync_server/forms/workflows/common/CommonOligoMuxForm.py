import pandas as pd

from flask import url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType, FeatureType, MUXType

from .... import logger, tools, db
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput, SpreadSheetColumn
from ....tools.spread_sheet_components import TextColumn, InvalidCellValue, MissingCellValue, CategoricalDropDown, DropdownColumn, DuplicateCellValue


class CommonOligoMuxForm(MultiStepForm):
    _step_name = "oligo_mux_annotation"
    spreadsheet: SpreadsheetInput
    library_table: pd.DataFrame
    df: pd.DataFrame
    index_col: str

    @staticmethod
    def is_abc_hashed(current_step: MultiStepForm) -> bool:
        return current_step.metadata.get("mux_type_id") == MUXType.TENX_ABC_HASH.id

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        if CommonOligoMuxForm.is_abc_hashed(current_step):
            return True
        return bool(current_step.tables["library_table"]["library_type_id"].isin([LibraryType.TENX_MUX_OLIGO.id]).any())
    
    @staticmethod
    def get_mux_table(sample_pooling_table: pd.DataFrame) -> pd.DataFrame:
        df = sample_pooling_table.copy()
        if "mux_read" not in df.columns:
            df["mux_read"] = None
        if "mux_pattern" not in df.columns:
            df["mux_pattern"] = None
        if "mux_barcode" not in df.columns:
            df["mux_barcode"] = None

        mux_data = {
            "sample_name": [],
            "sample_pool": [],
            "barcode": [],
            "pattern": [],
            "read": [],
        }
        for (sample_name, sample_pool, mux_barcode, mux_pattern, mux_read), _ in df.groupby(["sample_name", "sample_pool", "mux_barcode", "mux_pattern", "mux_read"], dropna=False, sort=False):
            mux_data["sample_name"].append(sample_name)
            mux_data["sample_pool"].append(sample_pool)
            mux_data["barcode"].append(mux_barcode)
            mux_data["pattern"].append(mux_pattern)
            mux_data["read"].append(mux_read)

        return pd.DataFrame(mux_data)

    def __init__(
        self,
        workflow: str,
        seq_request: models.SeqRequest | None,
        lab_prep: models.LabPrep | None,
        library: models.Library | None,
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
        self.library = library
        self.kits = []

        self.kits_mapping = {kit.identifier: f"[{kit.identifier}] {kit.name}" for kit in db.feature_kits.find(limit=None, sort_by="name", type=FeatureType.CMO)[0]}

        if workflow == "mux_prep":
            self.index_col = "library_id"
            if self.lab_prep is None:
                logger.error("LabPrep must be provided for mux_prep workflow")
                raise ValueError("LabPrep must be provided for mux_prep workflow")
            self.pooling_table = db.pd.get_lab_prep_pooling_table(self.lab_prep.id, expand_mux=True)
            self.pooling_table = self.pooling_table[self.pooling_table["mux_type_id"].isin([MUXType.TENX_OLIGO.id, MUXType.TENX_ABC_HASH.id])]
            self.mux_table = CommonOligoMuxForm.get_mux_table(self.pooling_table)
        elif workflow == "library_annotation":
            self.index_col = "sample_name"
            self.pooling_table = self.tables["sample_pooling_table"]
            self.pooling_table = self.pooling_table[self.pooling_table["mux_type_id"].isin([MUXType.TENX_OLIGO.id, MUXType.TENX_ABC_HASH.id])]
            self.mux_table = CommonOligoMuxForm.get_mux_table(self.pooling_table)
        elif workflow == "library_remux":
            if self.library is None:
                logger.error("Library must be provided for library_remux workflow")
                raise ValueError("Library must be provided for library_remux workflow")
            self.index_col = "library_id"
            data = {
                "sample_id": [],
                "sample_name": [],
                "barcode": [],
                "pattern": [],
                "read": [],
            }
            for link in self.library.sample_links:
                data["sample_id"].append(link.sample.id)
                data["sample_name"].append(link.sample.name)
                data["barcode"].append(link.mux.get("barcode") if link.mux is not None else None)
                data["pattern"].append(link.mux.get("pattern") if link.mux is not None else None)
                data["read"].append(link.mux.get("read") if link.mux is not None else None)

            self.pooling_table = pd.DataFrame(data)
            self.pooling_table["library_id"] = self.library.id
            self.pooling_table["sample_pool"] = self.library.sample_name

            self.mux_table = self.pooling_table[["sample_name", "sample_pool", "barcode", "pattern", "read"]].copy()
        else:
            logger.error(f"Unsupported workflow: {workflow}")
            raise ValueError(f"Unsupported workflow: {workflow}")

        columns = [
            TextColumn("sample_name", "Sample Name", 170, required=True, read_only=True),
            TextColumn("sample_pool", "Multiplexing Pool", 170, required=True, read_only=True),
            CategoricalDropDown("kit", "Kit", 250, categories=self.kits_mapping, required=False),
            TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
            TextColumn("barcode", "Sequence", 200, max_length=models.Feature.sequence.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
            TextColumn("pattern", "Pattern", 180, max_length=models.Feature.pattern.type.length, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
            DropdownColumn("read", "Read", 80, choices=["R2", "R1"]),
        ]

        self.columns = additional_columns + columns

        self.url_context = {}
        if self.seq_request is not None:
            self._context["seq_request"] = self.seq_request
            self.url_context["seq_request_id"] = self.seq_request.id
        if self.lab_prep is not None:
            self._context["lab_prep"] = self.lab_prep
            self.url_context["lab_prep_id"] = self.lab_prep.id
        if self.library is not None:
            self._context["library"] = self.library
            self.url_context["library_id"] = self.library.id

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=self._csrf_token,
            post_url=url_for(f"{workflow}_workflow.parse_oligo_mux_reference", uuid=self.uuid, **self.url_context),
            formdata=formdata
        )

        if not formdata:
            self.spreadsheet.set_data(self.mux_table)

    def fill_previous_form(self):
        df = self.tables["sample_pooling_table"]
        df = df.drop_duplicates(subset=["sample_name"]).rename(columns={
            "sample_name": "sample_name",
        })
        self.spreadsheet.set_data(df)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        self.df = self.spreadsheet.df

        kit_feature = pd.notna(self.df["kit"]) & pd.notna(self.df["feature"])
        custom_feature = pd.notna(self.df["barcode"]) & pd.notna(self.df["pattern"]) & pd.notna(self.df["read"])
        invalid_feature = (pd.notna(self.df["kit"]) | pd.notna(self.df["feature"])) & (pd.notna(self.df["barcode"]) | pd.notna(self.df["pattern"]) | pd.notna(self.df["read"]))
        
        kit_identifiers = self.df["kit"].dropna().unique().tolist()
        kits: dict[str, tuple[models.FeatureKit, pd.DataFrame]] = dict()
        
        self.df["kit_id"] = None
        for identifier in kit_identifiers:
            kit = db.feature_kits[identifier]
            kit_df = db.pd.get_feature_kit_features(kit.id)
            kits[identifier] = (kit, kit_df)
            self.df.loc[self.df["kit"] == identifier, "kit_id"] = kit.id

        duplicate_oligo = (
            (self.df.duplicated(subset=["sample_pool", "barcode", "pattern", "read"], keep=False) & custom_feature) |
            (self.df.duplicated(subset=["sample_pool", "kit", "feature"], keep=False) & kit_feature)
        )

        for identifier, (kit, kit_df) in kits.items():
            view = self.df[self.df["kit"] == identifier]
            kit_df["barcode"] = kit_df["sequence"]
            mask = kit_df["name"].isin(view["feature"])

            for _, kit_row in kit_df[mask].iterrows():
                self.df.loc[
                    (self.df["kit"] == identifier) & (self.df["feature"] == kit_row["name"]),
                    ["barcode", "pattern", "read"]
                ] = kit_row[["barcode", "pattern", "read"]].values
                
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
                self.spreadsheet.add_error(idx, "barcode", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "pattern", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "read", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))

            # Defined both custom and kit feature
            elif custom_feature.at[idx] and kit_feature.at[idx]:
                self.spreadsheet.add_error(idx, "kit", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "feature", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "barcode", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "pattern", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "read", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))

            elif invalid_feature.at[idx]:
                if pd.notna(row["kit"]):
                    self.spreadsheet.add_error(idx, "kit", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                if pd.notna(row["feature"]):
                    self.spreadsheet.add_error(idx, "feature", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                if pd.notna(row["barcode"]):
                    self.spreadsheet.add_error(idx, "barcode", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                if pd.notna(row["pattern"]):
                    self.spreadsheet.add_error(idx, "pattern", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                if pd.notna(row["read"]):
                    self.spreadsheet.add_error(idx, "read", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))

            if duplicate_oligo.at[idx]:
                self.spreadsheet.add_error(idx, "barcode", DuplicateCellValue("Definitions must be unique for each sample."))
                self.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("Definitions must be unique for each sample."))
                self.spreadsheet.add_error(idx, "read", DuplicateCellValue("Definitions must be unique for each sample."))
                self.spreadsheet.add_error(idx, "kit", DuplicateCellValue("Definitions must be unique for each sample."))
                self.spreadsheet.add_error(idx, "feature", DuplicateCellValue("Definitions must be unique for each sample."))

        self.kits = kits
        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df["custom_feature"] = custom_feature
        self.df["kit_feature"] = kit_feature
        return True
