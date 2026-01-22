import os
import pandas as pd

from flask import url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType, IndexType, BarcodeOrientation

from ....core import exceptions
from ....core.RunTime import runtime
from .... import logger, tools, db  # noqa F401
from ....tools import utils
from ...MultiStepForm import MultiStepForm, StepFile
from ...SpreadsheetInput import SpreadsheetInput, SpreadSheetColumn
from ....tools.spread_sheet_components import TextColumn, InvalidCellValue, MissingCellValue, CategoricalDropDown


class CommonBarcodeInputForm(MultiStepForm):
    _step_name = "barcode_input"
    spreadsheet: SpreadsheetInput
    library_table: pd.DataFrame
    df: pd.DataFrame
    index_col: str

    @staticmethod
    def barcode_sequence_clean_up(sequence: str | None) -> str | None:
        if pd.isna(sequence) or sequence is None:
            return None
        
        sequence = tools.make_alpha_numeric(sequence, keep=[], replace_white_spaces_with="")
        sequence = sequence.upper()  # type: ignore
        return sequence

    def __init__(
        self,
        workflow: str,
        seq_request: models.SeqRequest | None,
        lab_prep: models.LabPrep | None,
        pool: models.Pool | None,
        formdata: dict | None,
        uuid: str | None,
        additional_columns: list[SpreadSheetColumn] = []
    ):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=workflow,
            step_name=CommonBarcodeInputForm._step_name,
            step_args={},
        )
        self.seq_request = seq_request
        self.lab_prep = lab_prep
        self.pool = pool

        self.i7_kit_mapping = {kit.identifier: f"[{kit.identifier}] {kit.name}" for kit in db.index_kits.find(limit=None, sort_by="name", type_in=[IndexType.DUAL_INDEX, IndexType.SINGLE_INDEX_I7, IndexType.COMBINATORIAL_DUAL_INDEX])[0]}
        self.i5_kit_mapping = {kit.identifier: f"[{kit.identifier}] {kit.name}" for kit in db.index_kits.find(limit=None, sort_by="name", type_in=[IndexType.DUAL_INDEX, IndexType.COMBINATORIAL_DUAL_INDEX])[0]}

        columns = [
            TextColumn("library_name", "Library Name", 250, required=True, read_only=True),
            TextColumn("index_well", "Index Well", 100, max_length=8),
            CategoricalDropDown("kit_i7", "i7 Kit", 200, categories=self.i7_kit_mapping, required=False),
            TextColumn("name_i7", "i7 Name", 150, max_length=models.LibraryIndex.name_i7.type.length),
            TextColumn("sequence_i7", "i7 Sequence", 180, clean_up_fnc=CommonBarcodeInputForm.barcode_sequence_clean_up),
            CategoricalDropDown("kit_i5", "i5 Kit", 200, categories=self.i5_kit_mapping, required=False),
            TextColumn("name_i5", "i5 Name", 150, max_length=models.LibraryIndex.name_i5.type.length),
            TextColumn("sequence_i5", "i5 Sequence", 180, clean_up_fnc=CommonBarcodeInputForm.barcode_sequence_clean_up),
        ]
        self.columns = additional_columns + columns

        if workflow == "library_annotation":
            self.index_col = "library_name"
            if (library_table := self.tables.get("library_table")) is None:
                logger.error("Library table not found for library annotation workflow")
                raise exceptions.InternalServerErrorException("Library table not found for library annotation workflow")
            self.library_table = library_table
        elif workflow == "library_pooling":
            self.index_col = "library_id"
            if self.lab_prep is None:
                logger.error("lab_prep must be provided for library pooling workflow")
                raise ValueError("lab_prep must be provided for library pooling workflow")
            
            library_table = utils.get_barcode_table(db, self.lab_prep.libraries)
            if self.lab_prep.prep_file is not None:
                prep_table = pd.read_excel(os.path.join(runtime.app.media_folder, self.lab_prep.prep_file.path), "prep_table")  # type: ignore
                prep_table = prep_table.dropna(subset=["library_id", "library_name"])
                self.library_table = prep_table[[col.label for col in self.columns if col.label in prep_table.columns]]
                self.library_table["library_id"] = self.library_table["library_id"].astype(int)
                self.library_table["library_type_id"] = utils.map_columns(library_table, library_table, "library_id", "library_type_id").astype(int)
                self.library_table["kit_i7"] = self.library_table["kit_i7"].apply(lambda x: x if pd.isna(x) else str(x).strip().removeprefix("#"))
                self.library_table["kit_i5"] = self.library_table["kit_i5"].apply(lambda x: x if pd.isna(x) else str(x).strip().removeprefix("#"))
                self.library_table["index_well"] = self.library_table["index_well"].apply(lambda x: x if pd.isna(x) else str(x).strip())
                self.library_table["name_i7"] = self.library_table["name_i7"].apply(lambda x: x if pd.isna(x) else str(x).strip())
                self.library_table["name_i5"] = self.library_table["name_i5"].apply(lambda x: x if pd.isna(x) else str(x).strip())
            else:
                self.library_table = library_table
        elif workflow == "reindex":
            self.index_col = "library_id"
            if (library_table := self.tables.get("library_table")) is None:
                logger.error("Library table not found for reindex workflow")
                raise exceptions.InternalServerErrorException("Library table not found for reindex workflow")
            
            if self.lab_prep is not None:
                if self.lab_prep.prep_file is not None:
                    prep_table = pd.read_excel(os.path.join(runtime.app.media_folder, self.lab_prep.prep_file.path), "prep_table")  # type: ignore
                    prep_table = prep_table.dropna(subset=["library_id", "library_name"])
                    prep_table["library_id"] = prep_table["library_id"].astype(int)

                    def clean_value(value) -> str:
                        if pd.isna(value):
                            return ""
                        try:
                            value = int(value)
                            return str(value)
                        except ValueError:
                            pass
                        value = str(value).strip().removeprefix("#")
                        return value
                    
                    prep_table["kit_i7"] = prep_table["kit_i7"].apply(clean_value).astype(str)
                    prep_table["kit_i5"] = prep_table["kit_i5"].apply(clean_value).astype(str)
                    prep_table["index_well"] = prep_table["index_well"].apply(lambda x: x if pd.isna(x) else str(x).strip())
                    prep_table["name_i7"] = prep_table["name_i7"].apply(lambda x: x if pd.isna(x) else str(x).strip())
                    prep_table["name_i5"] = prep_table["name_i5"].apply(lambda x: x if pd.isna(x) else str(x).strip())


                    for idx, row in library_table[library_table["sequence_i7"].isna()].iterrows():
                        library_table.at[idx, "kit_i7"] = next(iter(prep_table[  # type: ignore
                            (prep_table["library_id"] == row["library_id"])
                        ]["kit_i7"].values.tolist()), None)
                        library_table.at[idx, "kit_i5"] = next(iter(prep_table[  # type: ignore
                            (prep_table["library_id"] == row["library_id"])
                        ]["kit_i5"].values.tolist()), None)
                        library_table.at[idx, "index_well"] = next(iter(prep_table[  # type: ignore
                            (prep_table["library_id"] == row["library_id"])
                        ]["index_well"].values.tolist()), None)
                        library_table.at[idx, "name_i7"] = next(iter(prep_table[  # type: ignore
                            (prep_table["library_id"] == row["library_id"])
                        ]["name_i7"].values.tolist()), None)
                        library_table.at[idx, "name_i5"] = next(iter(prep_table[  # type: ignore
                            (prep_table["library_id"] == row["library_id"])
                        ]["name_i5"].values.tolist()), None)
                    logger.debug(library_table)
                        
            self.library_table = library_table
        else:
            raise exceptions.InternalServerErrorException(f"Workflow '{workflow}' not supported in CommonBarcodeInputForm")
        
        logger.debug(self.library_table)

        if self.index_col not in [col.label for col in self.columns]:
            logger.error(f"Index column '{self.index_col}' not found in columns")
            raise exceptions.InternalServerErrorException(f"Index column '{self.index_col}' not found in columns")

        self.barcode_table = self.library_table[
            self.library_table["library_type_id"] != LibraryType.TENX_SC_ATAC.id
        ].copy()

        if self.index_col not in self.barcode_table.columns:
            logger.error(f"Index column '{self.index_col}' not found in barcode_table")
            raise exceptions.InternalServerErrorException(f"Index column '{self.index_col}' not found in barcode_table")

        self.url_context = {}
        if seq_request is not None:
            self._context["seq_request"] = seq_request
            self.url_context["seq_request_id"] = seq_request.id
        if lab_prep is not None:
            self._context["lab_prep"] = lab_prep
            self.url_context["lab_prep_id"] = lab_prep.id
        if pool is not None:
            self._context["pool"] = pool
            self.url_context["pool_id"] = pool.id
        
        self.post_url = url_for(f"{workflow}_workflow.upload_barcode_form", uuid=self.uuid, **self.url_context)
            
        self.spreadsheet = SpreadsheetInput(
            columns=self.columns,
            csrf_token=self._csrf_token,
            post_url=self.post_url, formdata=formdata, df=self.barcode_table
        )
        self.kits = []

    def fill_previous_form(self, previous_form: StepFile):
        barcode_table = previous_form.tables["barcode_table"]
        barcode_table = barcode_table[barcode_table["index_type_id"] != IndexType.TENX_ATAC_INDEX.id].copy()
        self.spreadsheet.set_data(barcode_table)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        self.df = self.spreadsheet.df

        self.df.loc[self.df["kit_i7"].notna(), "kit_i7"] = self.df.loc[self.df["kit_i7"].notna(), "kit_i7"].astype(str).str.strip()
        self.df.loc[self.df["kit_i5"].notna(), "kit_i5"] = self.df.loc[self.df["kit_i5"].notna(), "kit_i5"].astype(str).str.strip()
        self.df.loc[self.df["name_i7"].notna(), "name_i7"] = self.df.loc[self.df["name_i7"].notna(), "name_i7"].astype(str).str.strip()
        self.df.loc[self.df["name_i5"].notna(), "name_i5"] = self.df.loc[self.df["name_i5"].notna(), "name_i5"].astype(str).str.strip()
        self.df.loc[self.df["index_well"].notna(), "index_well"] = self.df.loc[self.df["index_well"].notna(), "index_well"].astype(str).str.strip()

        self.df.loc[self.df["index_well"].notna(), "index_well"] = self.df.loc[self.df["index_well"].notna(), "index_well"].str.strip().str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

        kit_defined = self.df["kit_i7"].notna() & (self.df["index_well"].notna() | self.df["name_i7"].notna())
        manual_defined = self.df["sequence_i7"].notna()

        # self.df.loc[self.df["kit_i5"].isna(), "kit_i5"] = self.df.loc[self.df["kit_i5"].isna(), "kit_i7"]
        # self.df.loc[self.df["name_i5"].isna(), "name_i5"] = self.df.loc[self.df["name_i5"].isna(), "name_i7"]

        kit_identifiers = list(set(self.df["kit_i7"].dropna().unique().tolist() + self.df["kit_i5"].dropna().unique().tolist()))
        kits: dict[str, tuple[models.IndexKit, pd.DataFrame]] = dict()

        self.df["kit_i7_id"] = None
        self.df["kit_i5_id"] = None

        for identifier in kit_identifiers:
            kit = db.index_kits[identifier]
            
            if kit.type in [IndexType.DUAL_INDEX, IndexType.COMBINATORIAL_DUAL_INDEX]:
                idx = (self.df["kit_i5"].isna() & (self.df["kit_i7"] == identifier))
                self.df.loc[idx, "kit_i5"] = self.df.loc[idx, "kit_i7"]
                
            if kit.type == IndexType.DUAL_INDEX:
                idx = (self.df["name_i5"].isna() & (self.df["kit_i7"] == identifier))
                self.df.loc[idx, "name_i5"] = self.df.loc[idx, "name_i7"]
            
            df = db.pd.get_index_kit_barcodes(kit.id, per_adapter=False, per_index=True)
            kits[identifier] = (kit, df)
            self.df.loc[self.df["kit_i7"] == identifier, "kit_i7_id"] = kit.id
            self.df.loc[self.df["kit_i5"] == identifier, "kit_i5_id"] = kit.id

        for kit_identifier, (kit, kit_df) in kits.items():
            view = self.df[(self.df["kit_i7"] == kit_identifier) | (self.df["kit_i5"] == kit_identifier)]
            
            match kit.type:
                case IndexType.DUAL_INDEX:
                    mask = (
                        (kit_df["well"].isin(view["index_well"].values)) |
                        (kit_df["name_i7"].isin(view["name_i7"].values)) |
                        (kit_df["name_i5"].isin(view["name_i5"].values))
                    )
                case IndexType.COMBINATORIAL_DUAL_INDEX:
                    mask = (
                        (kit_df["name_i7"].isin(view["name_i7"].values)) |
                        (kit_df["name_i5"].isin(view["name_i5"].values))
                    )
                case IndexType.SINGLE_INDEX_I7:
                    mask = (
                        (kit_df["well"].isin(view["index_well"].values)) |
                        (kit_df["name_i7"].isin(view["name_i7"].values))
                    )
                case _:
                    raise exceptions.InternalServerErrorException(f"Only Dual and Single index kits are supported, but kit '{kit.identifier}' is of type '{kit.type.name}'")
            
            for _, kit_row in kit_df[mask].iterrows():
                if "well" in kit_row:
                    self.df.loc[
                        (self.df["kit_i7"] == kit_identifier) &
                        (self.df["index_well"] == kit_row["well"]), "name_i7"
                    ] = kit_row["name_i7"]

                    self.df.loc[
                        (self.df["kit_i7"] == kit_identifier) &
                        (self.df["index_well"] == kit_row["well"]), "sequence_i7"
                    ] = kit_row["sequence_i7"]

                self.df.loc[
                    (self.df["kit_i7"] == kit_identifier) &
                    (self.df["name_i7"] == kit_row["name_i7"]), "sequence_i7"
                ] = kit_row["sequence_i7"]

                if kit.type in {IndexType.DUAL_INDEX, IndexType.COMBINATORIAL_DUAL_INDEX}:
                    if "well" in kit_row:
                        self.df.loc[
                            (self.df["kit_i5"] == kit_identifier) &
                            (self.df["index_well"] == kit_row["well"]), "name_i5"
                        ] = kit_row["name_i5"]

                        self.df.loc[
                            (self.df["kit_i5"] == kit_identifier) &
                            (self.df["index_well"] == kit_row["well"]), "sequence_i5"
                        ] = kit_row["sequence_i5"]

                    self.df.loc[
                        (self.df["kit_i5"] == kit_identifier) &
                        (self.df["name_i5"] == kit_row["name_i5"]), "sequence_i5"
                    ] = kit_row["sequence_i5"]

        for idx, row in self.df.iterrows():
            if row["index_well"] == "del":
                continue
                
            if pd.notna(row["kit_i7"]):
                if pd.isna(row["index_well"]) and pd.isna(row["name_i7"]):
                    self.spreadsheet.add_error(idx, ["index_well", "name_i7"], MissingCellValue("'index_well' or 'name_i7' must be defined when kit is defined"))
                    continue
            
            if pd.notna(row["kit_i5"]) and pd.notna(row["sequence_i5"]):
                if pd.isna(row["index_well"]) and pd.isna(row["name_i5"]):
                    self.spreadsheet.add_error(idx, ["index_well", "name_i5"], MissingCellValue("'index_well' or 'name_i5' must be defined when kit is defined"))
                    continue
            
            if row["library_name"] not in self.library_table["library_name"].values:
                self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name'"))

            if self._workflow_name == "library_pooling" and str(row["pool"]).strip().lower() == "x":
                continue

            if kit_defined.at[idx]:
                kit_i7_label = row["kit_i7"]
                kit_i7, kit_i7_df = kits[row["kit_i7"]]
                
                if pd.notna(row["name_i7"]):
                    if row["name_i7"] not in kit_i7_df["name_i7"].values:
                        self.spreadsheet.add_error(idx, "name_i7", InvalidCellValue(f"i7 name '{row['name_i7']}' not found in kit '{kit_i7_label}'"))
                        continue
                elif pd.notna(row["index_well"]):
                    if "well" not in kit_i7_df.columns or row["index_well"] not in kit_i7_df["well"].values:
                        self.spreadsheet.add_error(idx, "index_well", InvalidCellValue(f"i7 well '{row['index_well']}' not found in kit '{kit_i7_label}'"))
                        continue
                
                if pd.notna(row["kit_i5"]):
                    kit_i5, kit_i5_df = kits[row["kit_i5"]]
                    if kit_i5.type == IndexType.DUAL_INDEX:
                        kit_i5_label = row["kit_i5"]
                        if pd.notna(row["name_i5"]):
                            if row["name_i5"] not in kit_i5_df["name_i5"].values:
                                self.spreadsheet.add_error(idx, "name_i5", InvalidCellValue(f"i5 name '{row['name_i5']}' not found in kit '{kit_i5_label}'"))
                                continue
                        elif pd.notna(row["index_well"]) and "well" in kit_i5_df.columns:
                            if row["index_well"] not in kit_i5_df["well"].values:
                                self.spreadsheet.add_error(idx, "index_well", InvalidCellValue(f"i5 well '{row['index_well']}' not found in kit '{kit_i5_label}'"))
                                continue

            elif manual_defined.at[idx]:
                if pd.notna(row["sequence_i7"]) and len(row["sequence_i7"]) > models.LibraryIndex.sequence_i7.type.length:
                    self.spreadsheet.add_error(idx, "sequence_i7", InvalidCellValue(f"i7 sequence too long ({len(row['sequence_i7'])} > {models.LibraryIndex.sequence_i7.type.length})"))
                    continue
                
                if pd.notna(row["sequence_i5"]) and len(row["sequence_i5"]) > models.LibraryIndex.sequence_i5.type.length:
                    self.spreadsheet.add_error(idx, "sequence_i5", InvalidCellValue(f"i5 sequence too long ({len(row['sequence_i5'])} > {models.LibraryIndex.sequence_i5.type.length})"))
                    continue

            else:
                if pd.notna(row["kit_i7"]):
                    if pd.isna(row["index_well"]) and pd.isna(row["name_i7"]):
                        self.spreadsheet.add_error(idx, ["index_well", "name_i7"], MissingCellValue("'index_well' or 'name_i7' must be defined when kit is defined"))
                        continue
                elif pd.notna(row["index_well"]) or pd.notna(row["name_i7"]):
                    self.spreadsheet.add_error(idx, ["kit_i7", "name_i7"], MissingCellValue("missing 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well' or 'sequence_i7'"))
                    continue
                elif pd.isna(row["sequence_i7"]):
                    self.spreadsheet.add_error(idx, ["kit_i7", "name_i7"], MissingCellValue("missing 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well' or 'sequence_i7'"))
                    continue
                
            if pd.isna(row["sequence_i7"]):
                self.spreadsheet.add_error(idx, "sequence_i7", MissingCellValue("missing 'sequence_i7'"))
                continue

        self.df["index_type_id"] = None
        self.df.loc[(self.df["sequence_i7"].notna() & self.df["sequence_i5"].notna()), "index_type_id"] = IndexType.DUAL_INDEX.id
        self.df.loc[(self.df["sequence_i7"].notna() & self.df["sequence_i5"].isna()), "index_type_id"] = IndexType.SINGLE_INDEX_I7.id
        
        self.df["orientation_i7_id"] = None
        self.df["orientation_i5_id"] = None
        self.df.loc[(self.df["kit_i7_id"].notna()), "orientation_i7_id"] = BarcodeOrientation.FORWARD.id
        self.df.loc[self.df["kit_i5_id"].notna() & (self.df["index_type_id"] == IndexType.DUAL_INDEX.id), "orientation_i5_id"] = BarcodeOrientation.FORWARD.id
        
        self.spreadsheet.set_data(self.df)
        self.kits = kits
        return len(self.spreadsheet._errors) == 0