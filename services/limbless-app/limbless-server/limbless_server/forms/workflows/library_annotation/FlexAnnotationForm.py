from typing import Optional

import pandas as pd

from flask import Response, url_for
from wtforms import BooleanField

from opengsync_db import models
from opengsync_db.categories import LibraryType, MUXType, SubmissionType

from .... import logger, tools, db
from ....tools.spread_sheet_components import TextColumn, DropdownColumn, DuplicateCellValue
from ...SpreadsheetInput import SpreadsheetInput
from ...MultiStepForm import MultiStepForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm


class FlexAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-flex_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "flex_annotation"

    columns = [
        DropdownColumn("sample_name", "Sample (Pool) Name", 250, choices=[], required=True),
        TextColumn("demux_name", "Demultiplexed Sample Name", 250, clean_up_fnc=tools.make_alpha_numeric, required=True, max_length=models.Sample.name.type.length, min_length=4),
        TextColumn("barcode_id", "Bardcode ID", 250, max_length=16),
    ]

    single_plex = BooleanField("Single-Plex (do not fill the spreadsheet)", description="Samples were not multiplexed, i.e. one sample per library.", default=False)

    @staticmethod
    def is_applicable(current_step: MultiStepForm, seq_request: models.SeqRequest) -> bool:
        return (
            seq_request.submission_type in [SubmissionType.POOLED_LIBRARIES, SubmissionType.UNPOOLED_LIBRARIES] and
            LibraryType.TENX_SC_GEX_FLEX.id in current_step.tables["library_table"]["library_type_id"].values
        )

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
            if duplicate_barcode.at[idx]:
                self.spreadsheet.add_error(idx, "barcode_id", DuplicateCellValue("'Barcode ID' is not unique in the library."))

            if duplicate_samples.at[idx]:
                self.spreadsheet.add_error(idx, "demux_name", DuplicateCellValue("'Sample Name' is not unique in the library."))

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
            sample_pooling_table = self.tables["sample_pooling_table"]

            sample_data = {
                "sample_name": [],
            }

            pooling_data = {
                "sample_name": [],
                "library_name": [],
                "sample_pool": [],
                "mux_barcode": [],
                "mux_type_id": [],
            }

            for _, flex_row in self.flex_table.iterrows():
                sample_data["sample_name"].append(flex_row["demux_name"])
                for _, pooling_row in sample_pooling_table[sample_pooling_table["sample_name"] == flex_row["sample_name"]].iterrows():
                    pooling_data["sample_name"].append(flex_row["demux_name"])
                    pooling_data["library_name"].append(pooling_row["library_name"])
                    pooling_data["mux_barcode"].append(flex_row["barcode_id"])
                    pooling_data["sample_pool"].append(flex_row["sample_name"])

            sample_pooling_table = pd.DataFrame(pooling_data)
            self.update_table("sample_pooling_table", sample_pooling_table, update_data=False)
            
            sample_table = pd.DataFrame(sample_data)
            sample_table["sample_id"] = None
            if (project_id := self.metadata.get("project_id")) is not None:
                if (project := db.get_project(project_id)) is None:
                    logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
                    raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
                
                for sample in project.samples:
                    sample_table.loc[sample_table["sample_name"] == sample.name, "sample_id"] = sample.id

            self.update_table("sample_table", sample_table, update_data=False)
            self.add_table("flex_table", self.flex_table)
            self.update_data()
        
        next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return next_form.make_response()