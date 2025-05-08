from typing import Optional

import pandas as pd

from flask import Response, url_for
from wtforms import BooleanField

from limbless_db import models
from limbless_db.categories import LibraryType

from .... import logger, tools, db
from ....tools import SpreadSheetColumn, StaticSpreadSheet, TextColumn, DropdownColumn
from ...SpreadsheetInput import SpreadsheetInput
from ...MultiStepForm import MultiStepForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm


class FlexAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-flex_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "flex_annotation"

    columns = [
        DropdownColumn("sample_name", "Sample (Pool) Name", 250, choices=[], required=True),
        TextColumn("demux_name", "Demultiplexed Sample Name", 250, clean_up_fnc=tools.make_alpha_numeric, required=True),
        TextColumn("barcode_id", "Bardcode ID", 250),
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
        
        self.library_table = self.tables["library_table"]
        self.flex_table = self.library_table[self.library_table['library_type_id'] == LibraryType.TENX_SC_GEX_FLEX.id]
        self.flex_samples = self.flex_table["sample_name"].unique().tolist()
        
        self._context["available_samples"] = StaticSpreadSheet(
            df=self.flex_table,
            columns=[SpreadSheetColumn("sample_name", "Sample Name", "text", 500, str)],
        )

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=FlexAnnotationForm.columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_flex_annotation', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )

        self.spreadsheet.columns["sample_name"].source = self.flex_samples

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
            if row["sample_name"] not in self.flex_table["sample_name"].values:
                self.spreadsheet.add_error(idx, "sample_name", f"Unknown sample '{row['sample_name']}'. Must be one of: {', '.join(self.flex_table['sample_name'])}", "invalid_value")
            elif duplicate_barcode.at[idx]:
                self.spreadsheet.add_error(idx, "barcode_id", "'Barcode ID' is not unique in the library.", "duplicate_value")

            if duplicate_samples.at[idx]:
                self.spreadsheet.add_error(idx, "demux_name", "'Sample Name' is not unique in the library.", "duplicate_value")

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
            
            sample_table = self.tables["sample_table"]
            pooling_table = self.tables["pooling_table"]
            logger.debug(pooling_table)
            sample_data = {
                "sample_name": [],
                "flex_barcode": [],
            }

            pooling_data = {
                "sample_name": [],
                "library_name": [],
            }

            for _, flex_row in self.flex_table.iterrows():
                sample_data["sample_name"].append(flex_row["demux_name"])
                sample_data["flex_barcode"].append(flex_row["barcode_id"])
                for _, pooling_row in pooling_table[pooling_table["sample_name"] == flex_row["sample_name"]].iterrows():
                    pooling_data["sample_name"].append(flex_row["demux_name"])
                    pooling_data["library_name"].append(pooling_row["library_name"])

            sample_table = pd.DataFrame(sample_data)
            sample_table["cmo_sequence"] = None
            sample_table["cmo_pattern"] = None
            sample_table["cmo_read"] = None
            sample_table["sample_id"] = None
            pooling_table = pd.DataFrame(pooling_data)
            logger.debug(pooling_table)

            if (project_id := self.metadata.get("project_id")) is not None:
                if (project := db.get_project(project_id)) is None:
                    logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
                    raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
                
                for sample in project.samples:
                    sample_table.loc[sample_table["sample_name"] == sample.name, "sample_id"] = sample.id

            self.update_table("sample_table", sample_table, update_data=False)
            self.update_table("pooling_table", pooling_table, update_data=False)
            self.add_table("flex_table", self.flex_table)
            self.update_data()
        
        next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return next_form.make_response()