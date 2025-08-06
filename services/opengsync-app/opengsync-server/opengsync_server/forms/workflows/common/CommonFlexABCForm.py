from typing import Optional

import pandas as pd

from flask import url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType, MUXType

from .... import logger, tools, db  # noqa F401
from ....tools.spread_sheet_components import InvalidCellValue, DuplicateCellValue
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput, SpreadSheetColumn


class CommonFlexABCForm(MultiStepForm):
    _workflow_name: str
    _step_name = "flex_abc_annotation"
    df: pd.DataFrame
    index_col: str

    allowed_barcodes = [f"AB{i:03}" for i in range(1, 17)]
    mux_type = MUXType.TENX_FLEX_PROBE

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        sample_table = current_step.tables["sample_table"]
        return LibraryType.TENX_SC_ABC_FLEX in sample_table["library_type"].values

    def __init__(
        self,
        workflow: str,
        lab_prep: models.LabPrep | None,
        seq_request: models.SeqRequest | None,
        library: models.Library | None,
        columns: list[SpreadSheetColumn],
        formdata: dict | None = None,
        uuid: Optional[str] = None,
    ):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=workflow,
            step_name=CommonFlexABCForm._step_name, step_args={}
        )

        self.lab_prep = lab_prep
        self._context["lab_prep"] = self.lab_prep
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.library = library
        self._context["library"] = library
        self.columns = columns

        if workflow == "mux_prep":
            self.index_col = "library_id"
            if self.lab_prep is None:
                logger.error("LabPrep must be provided for mux_prep workflow")
                raise ValueError("LabPrep must be provided for mux_prep workflow")
            
            self.sample_table = self.tables["sample_table"]
            self.gex_table = self.tables["gex_table"]
            self.abc_table = self.sample_table[
                (self.sample_table["mux_type"].isin([MUXType.TENX_FLEX_PROBE])) &
                (self.sample_table["library_type"].isin([LibraryType.TENX_SC_ABC_FLEX]))
            ].copy()

        elif workflow == "library_remux":
            if self.library is None:
                logger.error("Library must be provided for library_remux workflow")
                raise ValueError("Library must be provided for library_remux workflow")
            self.index_col = "library_id"
            data = {
                "sample_id": [],
                "sample_name": [],
                "barcode_id": [],
            }
            for link in self.library.sample_links:
                data["sample_id"].append(link.sample.id)
                data["sample_name"].append(link.sample.name)
                data["barcode_id"].append(link.mux.get("barcode") if link.mux is not None else None)

            self.sample_table = pd.DataFrame(data)
            self.sample_table["library_id"] = self.library.id
            self.abc_table = self.sample_table.copy()
        else:
            logger.error(f"Workflow '{workflow}' is not supported for Flex ABC annotation.")
            raise Exception(f"Workflow '{workflow}' is not supported for Flex ABC annotation.")
        
        self.url_context = {}
        if self.seq_request is not None:
            self.url_context["seq_request_id"] = self.seq_request.id
            self._context["seq_request"] = self.seq_request
        elif self.lab_prep is not None:
            self.url_context["lab_prep_id"] = self.lab_prep.id
            self._context["lab_prep"] = self.lab_prep
        elif self.library is not None:
            self.url_context["library_id"] = self.library.id
            self._context["library"] = self.library
        
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=self._csrf_token,
            post_url=url_for(f"{workflow}_workflow.parse_flex_abc_annotation", uuid=self.uuid, **self.url_context),
            formdata=formdata
        )

    def prepare(self):
        df = self.abc_table
        self.spreadsheet.set_data(df)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        self.df = self.spreadsheet.df
        if self.workflow != "library_remux":
            self.df["sample_pool"] = self.gex_table.set_index("sample_name").loc[self.df["sample_name"], "sample_pool"].values
            duplicate_barcode = self.df.duplicated(subset=["sample_pool", "barcode_id"], keep=False)
        else:
            duplicate_barcode = pd.Series([False] * len(self.df), index=self.df.index)
        
        for idx, row in self.df.iterrows():
            if row["sample_name"] not in self.sample_table["sample_name"].values:
                self.spreadsheet.add_error(idx, "sample_name", InvalidCellValue(f"Unknown sample '{row['sample_name']}'. Must be one of: {', '.join(self.sample_table['sample_name'])}"))
            if pd.notna(row["barcode_id"]) and row["barcode_id"] not in CommonFlexABCForm.allowed_barcodes:
                self.spreadsheet.add_error(idx, "barcode_id", InvalidCellValue(f"'Barcode ID' must be one of: {', '.join(CommonFlexABCForm.allowed_barcodes)}"))
            if pd.notna(pd.isna(row["barcode_id"])) and duplicate_barcode.at[idx]:
                self.spreadsheet.add_error(idx, "barcode_id", DuplicateCellValue("'Barcode ID' is duplicated in library."))

        if len(self.spreadsheet._errors) > 0:
            return False

        return True