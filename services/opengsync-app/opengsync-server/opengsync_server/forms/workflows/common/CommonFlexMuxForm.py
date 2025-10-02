from typing import Optional

import pandas as pd

from flask import url_for

from opengsync_db import models, exceptions
from opengsync_db.categories import LibraryType, MUXType

from .... import logger, tools, db  # noqa F401
from ....tools.spread_sheet_components import InvalidCellValue
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput, SpreadSheetColumn


class CommonFlexMuxForm(MultiStepForm):
    _workflow_name: str
    _step_name = "flex_mux_annotation"
    df: pd.DataFrame
    index_col: str

    @staticmethod
    def padded_barcode_id(s: int | str | None) -> str | None:
        if pd.isna(s):
            return None
        number = ''.join(filter(str.isdigit, str(s)))
        return f"BC{number.zfill(3)}"

    allowed_barcodes = [f"BC{i:03}" for i in range(1, 17)]
    mux_type = MUXType.TENX_FLEX_PROBE

    def __init__(
        self,
        workflow: str,
        lab_prep: models.LabPrep | None,
        seq_request: models.SeqRequest | None,
        library: models.Library | None,
        formdata: dict | None = None,
        uuid: Optional[str] = None,
        columns: list[SpreadSheetColumn] = []
    ):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=workflow,
            step_name=CommonFlexMuxForm._step_name, step_args={}
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
            
            self.sample_table = db.pd.get_lab_prep_pooling_table(self.lab_prep.id)
            self.flex_table = self.sample_table[
                (self.sample_table["mux_type"].isin([MUXType.TENX_FLEX_PROBE])) &
                (self.sample_table["library_type"].isin([LibraryType.TENX_SC_GEX_FLEX]))
            ].copy()
            self.flex_table["barcode_id"] = self.sample_table["mux"].apply(
                lambda x: x.get("barcode") if pd.notna(x) and isinstance(x, dict) else None
            )
        elif workflow == "library_annotation":
            self.index_col = "sample_name"
            self.sample_table = self.tables["library_table"]
            self.flex_table = self.sample_table[self.sample_table['library_type_id'] == LibraryType.TENX_SC_GEX_FLEX.id]
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
            self.flex_table = self.sample_table.copy()
        else:
            logger.error(f"Unsupported workflow: {workflow}")
            raise ValueError(f"Unsupported workflow: {workflow}")

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

        self.post_url = url_for(f"{workflow}_workflow.parse_flex_annotation", uuid=self.uuid, **self.url_context)

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=self._csrf_token,
            post_url=self.post_url, formdata=formdata,
            allow_new_rows=workflow == "library_annotation"
        )

    def prepare(self):
        if self.workflow != "library_annotation":
            self.spreadsheet.set_data(self.flex_table)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df
        
        for idx, row in df.iterrows():
            if row["sample_name"] not in self.sample_table["sample_name"].values:
                self.spreadsheet.add_error(idx, "sample_name", InvalidCellValue(f"Unknown sample '{row['sample_name']}'. Must be one of: {', '.join(self.sample_table['sample_name'])}"))

            if pd.notna(row["barcode_id"]) and row["barcode_id"] not in CommonFlexMuxForm.allowed_barcodes:
                self.spreadsheet.add_error(idx, "barcode_id", InvalidCellValue(f"'Barcode ID' must be one of: {', '.join(CommonFlexMuxForm.allowed_barcodes)}"))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df

        return True
    
    @classmethod
    def update_barcodes(cls, sample_table: pd.DataFrame):
        for (sample_id, library_id, barcode), _df in sample_table.groupby(["sample_id", "library_id", "mux_barcode"]):
            if (link := db.links.get_sample_library_link(sample_id=int(sample_id), library_id=int(library_id))) is None:
                logger.error(f"SampleLibraryLink not found for sample_id={sample_id}, library_id={library_id}.")
                raise exceptions.ElementDoesNotExist(f"SampleLibraryLink not found for sample_id={sample_id}, library_id={library_id}.")
            
            if link.mux is None:
                link.mux = {}
            link.mux["barcode"] = str(barcode)
            db.links.update_sample_library_link(link)