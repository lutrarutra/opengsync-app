import os
import pandas as pd

from flask import url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType, IndexType

from ....core import exceptions
from ....core.RunTime import runtime
from .... import logger, db  # noqa F401
from ....tools.spread_sheet_components import TextColumn, InvalidCellValue, MissingCellValue
from .... import logger, tools, db  # noqa F401
from ....tools import utils
from ...SpreadsheetInput import SpreadsheetInput, SpreadSheetColumn
from ...MultiStepForm import MultiStepForm


class CommonTENXATACBarcodeInputForm(MultiStepForm):
    _step_name = "tenx_atac_barcode_input"
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
        TextColumn("kit", "Kit", 200, max_length=models.Kit.name.type.length),
        TextColumn("name", "Barcode Name", 150, max_length=models.LibraryIndex.name_i7.type.length),
        TextColumn("sequence_1", "Sequence 1", 180, clean_up_fnc=barcode_sequence_clean_up),
        TextColumn("sequence_2", "Sequence 2", 180, clean_up_fnc=barcode_sequence_clean_up),
        TextColumn("sequence_3", "Sequence 3", 180, clean_up_fnc=barcode_sequence_clean_up),
        TextColumn("sequence_4", "Sequence 4", 180, clean_up_fnc=barcode_sequence_clean_up),
    ]

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return bool((current_step.tables["library_table"]["library_type_id"] == LibraryType.TENX_SC_ATAC.id).any())

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
            step_name=CommonTENXATACBarcodeInputForm._step_name,
            step_args={},
        )
        self.seq_request = seq_request
        self.lab_prep = lab_prep
        self.pool = pool
        self.columns = additional_columns + CommonTENXATACBarcodeInputForm.columns

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
                    prep_table = prep_table.dropna(subset=["library_id", "library_name"]).rename(columns={"kit_i7": "kit", "name_i7": "name"})
                    self.library_table = prep_table[[col.label for col in self.columns if col.label in prep_table.columns]]
                    self.library_table["library_type_id"] = library_table.set_index(self.index_col).loc[self.library_table["library_id"], "library_type_id"].values
                else:
                    self.library_table = library_table
            else:
                logger.error(f"Library table not found for workflow {workflow}")
                raise exceptions.InternalServerErrorException("Library table not found for workflow")
        else:
            self.library_table = library_table

        self.barcode_table = self.library_table[
            self.library_table["library_type_id"] == LibraryType.TENX_SC_ATAC.id
        ].copy()

        if "sequence_i7" in self.barcode_table.columns:
            data = {
                self.index_col: [],
                "index_well": [],
                "kit": [],
                "name": [],
                "sequence_1": [],
                "sequence_2": [],
                "sequence_3": [],
                "sequence_4": [],
            }
            if "library_name" not in data.keys():
                data["library_name"] = []

            for _, row in self.barcode_table.iterrows():
                data[self.index_col].append(row[self.index_col])
                data["index_well"].append(row["index_well"])
                data["kit"].append(row["kit_i7"])
                data["name"].append(row["name_i7"])
                if self.index_col != "library_name":
                    data["library_name"].append(row["library_name"])
                for i, seq in enumerate(row["sequence_i7"].split(";") if pd.notna(row["sequence_i7"]) else [None] * 4):
                    data[f"sequence_{i + 1}"].append(seq)

            self.barcode_table = pd.DataFrame(data)
            
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
        
        self.post_url = url_for(f"{workflow}_workflow.upload_tenx_atac_barcode_form", uuid=self.uuid, **self.url_context)
            
        self.spreadsheet = SpreadsheetInput(
            columns=self.columns,
            csrf_token=self._csrf_token,
            post_url=self.post_url, formdata=formdata, df=self.barcode_table
        )

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        self.df = self.spreadsheet.df

        self.df.loc[self.df["kit"].notna(), "kit"] = self.df.loc[self.df["kit"].notna(), "kit"].astype(str)
        self.df.loc[self.df["index_well"].notna(), "index_well"] = self.df.loc[self.df["index_well"].notna(), "index_well"].str.strip().str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

        kit_defined = self.df["kit"].notna() & (self.df["index_well"].notna() | self.df["name"].notna())
        manual_defined = (
            self.df["sequence_1"].notna() &
            self.df["sequence_2"].notna() &
            self.df["sequence_3"].notna() &
            self.df["sequence_4"].notna()
        )

        for idx, row in self.df.iterrows():
            if row["library_name"] not in self.library_table["library_name"].values:
                self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name'"))

            if (not kit_defined.at[idx]) and (not manual_defined.at[idx]):
                if pd.notna(row["kit"]):
                    if pd.isna(row["index_well"]) and pd.isna(row["name"]):
                        self.spreadsheet.add_error(idx, ["index_well", "name"], MissingCellValue("'Index Well' or 'Name' must be defined when kit is defined"))
                elif pd.notna(row["index_well"]) or pd.notna(row["name"]):
                    self.spreadsheet.add_error(idx, "kit", MissingCellValue("missing 'Sequence 1/2/3/4' or 'Kit' + 'Name' or 'Index Well' + 'Kit'"))
                elif pd.isna(row["sequence_1"]):
                    self.spreadsheet.add_error(idx, ["kit", "name", "sequence_1", "sequence_2", "sequence_3", "sequence_4"], MissingCellValue("missing 'Sequence 1/2/3/4' or 'Name' + 'Kit' or 'Index Well' + 'Kit'"))
                elif pd.isna(row["sequence_2"]):
                    self.spreadsheet.add_error(idx, ["kit", "name", "sequence_1", "sequence_2", "sequence_3", "sequence_4"], MissingCellValue("missing 'Sequence 1/2/3/4' or 'Name' + 'Kit' or 'Index Well' + 'Kit'"))
                elif pd.isna(row["sequence_3"]):
                    self.spreadsheet.add_error(idx, ["kit", "name", "sequence_1", "sequence_2", "sequence_3", "sequence_4"], MissingCellValue("missing 'Sequence 1/2/3/4' or 'Name' + 'Kit' or 'Index Well' + 'Kit'"))
                elif pd.isna(row["sequence_4"]):
                    self.spreadsheet.add_error(idx, ["kit", "name", "sequence_1", "sequence_2", "sequence_3", "sequence_4"], MissingCellValue("missing 'Sequence 1/2/3/4' or 'Name' + 'Kit' or 'Index Well' + 'Kit'"))
        
        self.df["index_type_id"] = IndexType.TENX_ATAC_INDEX.id
        return len(self.spreadsheet._errors) == 0

    def get_barcode_table(self) -> pd.DataFrame:
        return self.df