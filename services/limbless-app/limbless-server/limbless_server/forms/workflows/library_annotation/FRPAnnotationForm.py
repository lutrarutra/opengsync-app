from typing import Optional

import pandas as pd

from flask import Response, url_for

from limbless_db import models
from limbless_db.categories import LibraryType

from .... import logger, tools
from ....tools import SpreadSheetColumn
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SpreadsheetInput import SpreadsheetInput
from ...TableDataForm import TableDataForm
from .SampleAnnotationForm import SampleAnnotationForm


class FRPAnnotationForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-10.html"

    columns = {
        "sample_name": SpreadSheetColumn("A", "sample_name", "Library Name", "text", 250, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        "barcode_id": SpreadSheetColumn("B", "barcode_id", "Bardcode ID", "text", 250, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
        "demux_name": SpreadSheetColumn("C", "demux_name", "Demux Name", "text", 250, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
    }

    def __init__(self, seq_request: models.SeqRequest, uuid: str, previous_form: Optional[TableDataForm] = None, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid, previous_form=previous_form)
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=FRPAnnotationForm.columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_frp_annotation', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )

    def get_template(self) -> pd.DataFrame:
        df = pd.DataFrame(columns=[col.name for col in FRPAnnotationForm.columns.values()])
        return df

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df
        
        library_table: pd.DataFrame = self.tables["library_table"]

        duplicate_barcode = df.duplicated(subset=["sample_name", "barcode_id"], keep=False)
        duplicate_samples = df.duplicated(subset=["sample_name", "demux_name"], keep=False)

        flex_libraries = library_table[library_table['library_type_id'] == LibraryType.TENX_SC_GEX_FLEX.id]

        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.isna(row["sample_name"]):
                self.spreadsheet.add_error(i + 1, "sample_name", "'Library Name' is missing.", "missing_value")
            elif row["sample_name"] not in library_table["sample_name"].values:
                self.spreadsheet.add_error(i + 1, "sample_name", f"Unknown sample '{row['sample_name']}'. Must be one of: {', '.join(flex_libraries['sample_name'])}", "invalid_value")
            elif duplicate_barcode.at[idx]:
                self.spreadsheet.add_error(i + 1, "barcode_id", "'Barcode ID' is not unique in the library.", "duplicate_value")

            if pd.isna(row["barcode_id"]):
                self.spreadsheet.add_error(i + 1, "barcode_id", "'Barcode ID' is missing.", "missing_value")
            
            if pd.isna(row["demux_name"]):
                self.spreadsheet.add_error(i + 1, "demux_name", "'Sample Name' is missing.", "missing_value")

            elif duplicate_samples.at[idx]:
                self.spreadsheet.add_error(i + 1, "demux_name", "'Sample Name' is not unique in the library.", "duplicate_value")

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.flex_table = df
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        if self.flex_table is None:
            logger.error(f"{self.uuid}: FRP table is None.")
            raise Exception("FRP table is None.")
        
        self.add_table("flex_table", self.flex_table)
        self.update_data()
        
        sample_annotation_form = SampleAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return sample_annotation_form.make_response()