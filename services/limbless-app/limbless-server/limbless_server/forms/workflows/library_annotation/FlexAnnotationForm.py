from typing import Optional

import pandas as pd

from flask import Response, url_for
from wtforms import BooleanField

from limbless_db import models
from limbless_db.categories import LibraryType

from .... import logger, tools
from ....tools import SpreadSheetColumn, StaticSpreadSheet
from ...SpreadsheetInput import SpreadsheetInput
from ...MultiStepForm import MultiStepForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm


class FlexAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-flex_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "flex_annotation"

    columns = [
        SpreadSheetColumn("sample_name", "Sample Name", "text", 250, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        SpreadSheetColumn("demux_name", "Demux Name", "text", 250, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        SpreadSheetColumn("barcode_id", "Bardcode ID", "text", 250, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
    ]

    single_plex = BooleanField("Single-Plex (do not fill the spreadsheet)", description="Samples were not multiplexed, i.e. one sample per library.", default=False)

    def __init__(self, seq_request: models.SeqRequest, uuid: str, previous_form: Optional[MultiStepForm] = None, formdata: dict = {}):
        MultiStepForm.__init__(
            self, workflow=FlexAnnotationForm._workflow_name, step_name=FlexAnnotationForm._step_name,
            uuid=uuid, formdata=formdata, previous_form=previous_form, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=FlexAnnotationForm.columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_flex_annotation', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )
        self.library_table = self.tables["library_table"]
        flex_libraries = self.library_table[self.library_table['library_type_id'] == LibraryType.TENX_SC_GEX_FLEX.id]
        
        self._context["available_samples"] = StaticSpreadSheet(
            df=flex_libraries,
            columns=[SpreadSheetColumn("sample_name", "Sample Name", "text", 500, str)],
        )

    def get_template(self) -> pd.DataFrame:
        df = pd.DataFrame(columns=[col.name for col in FlexAnnotationForm.columns])
        return df

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if self.single_plex.data:
            return True

        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df

        duplicate_barcode = df.duplicated(subset=["sample_name", "barcode_id"], keep=False)
        duplicate_samples = df.duplicated(subset=["sample_name", "demux_name"], keep=False)

        if (~self.flex_table["sample_name"].isin(df["sample_name"])).any():
            self.spreadsheet.add_general_error(f"Missing samples for library: {self.flex_table[~self.flex_table['sample_name'].isin(df['sample_name'])]['sample_name'].values.tolist()}")
            return False

        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.isna(row["sample_name"]):
                self.spreadsheet.add_error(i + 1, "sample_name", "'Library Name' is missing.", "missing_value")
            elif row["sample_name"] not in self.flex_table["sample_name"].values:
                self.spreadsheet.add_error(i + 1, "sample_name", f"Unknown sample '{row['sample_name']}'. Must be one of: {', '.join(self.flex_table['sample_name'])}", "invalid_value")
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
        
        if not self.single_plex.data:
            if self.flex_table is None:
                logger.error(f"{self.uuid}: Flex table is None.")
                raise Exception("Flex table is None.")
        
            self.add_table("flex_table", self.flex_table)
            self.update_data()
        
        next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return next_form.make_response()