import os
import pandas as pd

from flask import url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType, IndexType

from ....core import exceptions
from ....core.runtime import runtime
from .... import logger, tools, db  # noqa F401
from ....tools import utils
from ...MultiStepForm import MultiStepForm, StepFile
from ...SpreadsheetInput import SpreadsheetInput, SpreadSheetColumn
from ....tools.spread_sheet_components import TextColumn, InvalidCellValue, MissingCellValue


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

    columns = [
        TextColumn("library_name", "Library Name", 250, required=True, read_only=True),
        TextColumn("index_well", "Index Well", 100, max_length=8),
        TextColumn("kit_i7", "i7 Kit", 200, max_length=models.Kit.name.type.length),
        TextColumn("name_i7", "i7 Name", 150, max_length=models.LibraryIndex.name_i7.type.length),
        TextColumn("sequence_i7", "i7 Sequence", 180, clean_up_fnc=barcode_sequence_clean_up),
        TextColumn("kit_i5", "i5 Kit", 200, max_length=models.Kit.name.type.length),
        TextColumn("name_i5", "i5 Name", 150, max_length=models.LibraryIndex.name_i5.type.length),
        TextColumn("sequence_i5", "i5 Sequence", 180, clean_up_fnc=barcode_sequence_clean_up),
    ]

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
        self.columns = additional_columns + self.columns

        if workflow == "library_annotation":
            self.index_col = "library_name"
        else:
            self.index_col = "library_id"

        if self.index_col not in [col.label for col in self.columns]:
            logger.error(f"Index column '{self.index_col}' not found in columns")
            raise exceptions.InternalServerErrorException(f"Index column '{self.index_col}' not found in columns")
        
        if (library_table := self.tables.get("library_table")) is None:
            if workflow == "library_pooling":
                if self.lab_prep is None:
                    logger.error("lab_prep must be provided for library pooling workflow")
                    raise ValueError("lab_prep must be provided for library pooling workflow")
                
                library_table = utils.get_barcode_table(db, self.lab_prep.libraries)
                if self.lab_prep.prep_file is not None:
                    prep_table = pd.read_excel(os.path.join(runtime.current_app.media_folder, self.lab_prep.prep_file.path), "prep_table")  # type: ignore
                    prep_table = prep_table.dropna(subset=["library_id", "library_name"])
                    self.library_table = prep_table[[col.label for col in self.columns if col.label in prep_table.columns]]
                    self.library_table["library_type_id"] = library_table.set_index(self.index_col).loc[self.library_table["library_id"], "library_type_id"].values
                else:
                    self.library_table = library_table
            else:
                logger.error(f"Library table not found for workflow {workflow}")
                raise exceptions.WorkflowException("Library table not found for workflow")
        else:
            self.library_table = library_table

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

        self.df.loc[self.df["kit_i7"].notna(), "kit_i7"] = self.df.loc[self.df["kit_i7"].notna(), "kit_i7"].astype(str)
        self.df.loc[self.df["kit_i5"].notna(), "kit_i5"] = self.df.loc[self.df["kit_i5"].notna(), "kit_i5"].astype(str)

        self.df.loc[self.df["index_well"].notna(), "index_well"] = self.df.loc[self.df["index_well"].notna(), "index_well"].str.strip().str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

        kit_defined = self.df["kit_i7"].notna() & (self.df["index_well"].notna() | self.df["name_i7"].notna())
        manual_defined = self.df["sequence_i7"].notna()

        self.df.loc[self.df["kit_i5"].isna(), "kit_i5"] = self.df.loc[self.df["kit_i5"].isna(), "kit_i7"]
        self.df.loc[self.df["name_i5"].isna(), "name_i5"] = self.df.loc[self.df["name_i5"].isna(), "name_i7"]

        for idx, row in self.df.iterrows():
            if row["library_name"] not in self.library_table["library_name"].values:
                self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name'"))

            if self._workflow_name == "library_pooling" and str(row["pool"]).strip().lower() == "x":
                continue

            if (not kit_defined.at[idx]) and (not manual_defined.at[idx]):
                if pd.notna(row["kit_i7"]):
                    if pd.isna(row["index_well"]) and pd.isna(row["name_i7"]):
                        self.spreadsheet.add_error(idx, ["index_well", "name_i7"], MissingCellValue("'index_well' or 'name_i7' must be defined when kit is defined"))
                elif pd.notna(row["index_well"]) or pd.notna(row["name_i7"]):
                    self.spreadsheet.add_error(idx, "kit_i7", MissingCellValue("missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'"))
                elif pd.isna(row["sequence_i7"]):
                    self.spreadsheet.add_error(idx, "sequence_i7", MissingCellValue("missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'"))

            if pd.notna(row["sequence_i7"]) and len(row["sequence_i7"]) > models.LibraryIndex.sequence_i7.type.length:
                self.spreadsheet.add_error(idx, "sequence_i7", InvalidCellValue(f"i7 sequence too long ({len(row['sequence_i7'])} > {models.LibraryIndex.sequence_i7.type.length})"))
            
            if pd.notna(row["sequence_i5"]) and len(row["sequence_i5"]) > models.LibraryIndex.sequence_i5.type.length:
                self.spreadsheet.add_error(idx, "sequence_i5", InvalidCellValue(f"i5 sequence too long ({len(row['sequence_i5'])} > {models.LibraryIndex.sequence_i5.type.length})"))

        return len(self.spreadsheet._errors) == 0
    
    def get_barcode_table(self) -> pd.DataFrame:
        barcode_table_data = {
            self.index_col: [],
            "index_well": [],
            "kit_i7": [],
            "name_i7": [],
            "sequence_i7": [],
            "kit_i5": [],
            "name_i5": [],
            "sequence_i5": [],
        }
        
        for _, row in self.df.iterrows():
            index_i7_seqs = row["sequence_i7"].split(";") if pd.notna(row["sequence_i7"]) else [None]
            index_i5_seqs = row["sequence_i5"].split(";") if pd.notna(row["sequence_i5"]) else [None]

            for i in range(max(len(index_i7_seqs), len(index_i5_seqs))):
                barcode_table_data[self.index_col].append(row[self.index_col])
                barcode_table_data["index_well"].append(row["index_well"])
                barcode_table_data["kit_i7"].append(row["kit_i7"])
                barcode_table_data["name_i7"].append(row["name_i7"])
                barcode_table_data["sequence_i7"].append(index_i7_seqs[i] if len(index_i7_seqs) > i else None)
                barcode_table_data["kit_i5"].append(row["kit_i5"])
                barcode_table_data["name_i5"].append(row["name_i5"])
                barcode_table_data["sequence_i5"].append(index_i5_seqs[i] if len(index_i5_seqs) > i else None)

        barcode_table = pd.DataFrame(barcode_table_data)
        barcode_table["kit_i7_id"] = None
        barcode_table["kit_i7_name"] = None
        barcode_table["kit_i5_id"] = None
        barcode_table["kit_i5_name"] = None
        barcode_table["index_type_id"] = None

        barcode_table.loc[(barcode_table["sequence_i7"].notna() & barcode_table["sequence_i5"].notna()), "index_type_id"] = IndexType.DUAL_INDEX.id
        barcode_table.loc[(barcode_table["sequence_i7"].notna() & barcode_table["sequence_i5"].isna()), "index_type_id"] = IndexType.SINGLE_INDEX.id
        for (idx, library_type_id), _ in self.library_table.groupby([self.index_col, "library_type_id"], dropna=False):
            if LibraryType.get(library_type_id) == LibraryType.TENX_SC_ATAC:
                barcode_table.loc[barcode_table[self.index_col] == idx, "index_type_id"] = IndexType.TENX_ATAC_INDEX.id

        df = self.df.set_index(self.index_col)
        for col in df.columns:
            if col not in barcode_table.columns:
                barcode_table[col] = df.loc[barcode_table[self.index_col], col].values
        return barcode_table