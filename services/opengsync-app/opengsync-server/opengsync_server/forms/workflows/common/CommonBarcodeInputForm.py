import pandas as pd

from flask import url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType, IndexType

from .... import logger, tools, db  # noqa F401
from ....tools import utils
from ....tools import exceptions
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput, SpreadSheetColumn
from ....tools.spread_sheet_components import TextColumn, InvalidCellValue, MissingCellValue


class CommonBarcodeInputForm(MultiStepForm):
    _step_name = "barcode_input"
    spreadsheet: SpreadsheetInput
    library_table: pd.DataFrame
    df: pd.DataFrame
    index_col: str
    
    columns = [
        TextColumn("index_well", "Index Well", 100, max_length=8),
        TextColumn("kit_i7", "i7 Kit", 200, max_length=models.Kit.name.type.length),
        TextColumn("name_i7", "i7 Name", 150, max_length=models.LibraryIndex.name_i7.type.length),
        TextColumn("sequence_i7", "i7 Sequence", 180, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with="")),
        TextColumn("kit_i5", "i5 Kit", 200, max_length=models.Kit.name.type.length),
        TextColumn("name_i5", "i5 Name", 150, max_length=models.LibraryIndex.name_i5.type.length),
        TextColumn("sequence_i5", "i5 Sequence", 180, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with="")),
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

        if workflow == "library_annotation":
            self.index_col = "library_name"
        else:
            self.index_col = "library_id"

        if self.index_col not in [col.label for col in self.columns + additional_columns]:
            logger.error(f"Index column '{self.index_col}' not found in columns")
            raise exceptions.InternalServerErrorException(f"Index column '{self.index_col}' not found in columns")
        
        if (library_table := self.tables.get("library_table")) is None:
            if workflow == "library_pooling":
                if self.lab_prep is None:
                    logger.error("lab_prep must be provided for library pooling workflow")
                    raise ValueError("lab_prep must be provided for library pooling workflow")
                
                self.library_table = utils.get_barcode_table(db, self.lab_prep.libraries)
            else:
                logger.error(f"Library table not found for workflow {workflow}")
                raise exceptions.WorkflowException("Library table not found for workflow")
        else:
            self.library_table = library_table
        
        if self.index_col not in self.library_table.columns:
            logger.error(f"Index column '{self.index_col}' not found in library_table")
            raise exceptions.InternalServerErrorException(f"Index column '{self.index_col}' not found in library_table")

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
            
        self.columns = additional_columns + CommonBarcodeInputForm.columns
        self.spreadsheet = SpreadsheetInput(
            columns=self.columns,
            csrf_token=self._csrf_token,
            post_url=self.post_url, formdata=formdata, df=self.library_table
        )
        self.spreadsheet.columns["library_name"].source = self.library_table["library_name"].values.tolist() if self.library_table is not None else []

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        self.df = self.spreadsheet.df

        self.df.loc[self.df["kit_i7"].notna(), "kit_i7"] = self.df.loc[self.df["kit_i7"].notna(), "kit_i7"].astype(str)
        self.df.loc[self.df["kit_i5"].notna(), "kit_i5"] = self.df.loc[self.df["kit_i5"].notna(), "kit_i5"].astype(str)
            
        self.df["sequence_i7"] = self.df["sequence_i7"].apply(lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with=""))
        self.df["sequence_i5"] = self.df["sequence_i5"].apply(lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with=""))

        seq_i7_max_length = self.df["sequence_i7"].apply(lambda x: max(((len(s) for s in x.split(";") if pd.notna(s)) if pd.notna(x) else ""), default=0))
        seq_i5_max_length = self.df["sequence_i5"].apply(lambda x: max(((len(s) for s in x.split(";") if pd.notna(s)) if pd.notna(x) else ""), default=0))

        self.df.loc[self.df["index_well"].notna(), "index_well"] = self.df.loc[self.df["index_well"].notna(), "index_well"].str.strip().str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

        kit_defined = self.df["kit_i7"].notna() & (self.df["index_well"].notna() | self.df["name_i7"].notna())
        manual_defined = self.df["sequence_i7"].notna()

        self.df.loc[self.df["kit_i5"].isna(), "kit_i5"] = self.df.loc[self.df["kit_i5"].isna(), "kit_i7"]
        self.df.loc[self.df["name_i5"].isna(), "name_i5"] = self.df.loc[self.df["name_i5"].isna(), "name_i7"]

        for i, (idx, row) in enumerate(self.df.iterrows()):
            if row["library_name"] not in self.library_table["library_name"].values:
                self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name'"))

            if (not kit_defined.at[idx]) and (not manual_defined.at[idx]):
                if pd.notna(row["kit_i7"]):
                    if pd.isna(row["index_well"]) and pd.isna(row["name_i7"]):
                        self.spreadsheet.add_error(idx, ["index_well", "name_i7"], MissingCellValue("'index_well' or 'name_i7' must be defined when kit is defined"))
                elif pd.notna(row["index_well"]) or pd.notna(row["name_i7"]):
                    self.spreadsheet.add_error(idx, "kit_i7", MissingCellValue("missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'"))
                elif pd.isna(row["sequence_i7"]):
                    self.spreadsheet.add_error(idx, "sequence_i7", MissingCellValue("missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'"))

            if seq_i7_max_length.at[idx] > models.LibraryIndex.sequence_i7.type.length:
                self.spreadsheet.add_error(idx, "sequence_i7", InvalidCellValue(f"i7 sequence too long ({seq_i7_max_length.at[idx]} > {models.LibraryIndex.sequence_i7.type.length})"))
            
            if seq_i5_max_length.at[idx] > models.LibraryIndex.sequence_i5.type.length:
                self.spreadsheet.add_error(idx, "sequence_i5", InvalidCellValue(f"i5 sequence too long ({seq_i5_max_length.at[idx]} > {models.LibraryIndex.sequence_i5.type.length})"))

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

        return barcode_table