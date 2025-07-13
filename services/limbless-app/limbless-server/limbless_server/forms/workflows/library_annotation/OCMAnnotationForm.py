from typing import Optional

import pandas as pd

from flask import Response, url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType, FeatureType, MUXType

from .... import logger, tools, db  # noqa
from ....tools.spread_sheet_components import TextColumn, DropdownColumn, InvalidCellValue, DuplicateCellValue
from ...MultiStepForm import MultiStepForm, StepFile
from ...SpreadsheetInput import SpreadsheetInput
from .KitMappingForm import KitMappingForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm


class OCMAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-ocm_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "ocm_annotation"
    columns = [
        TextColumn("demux_name", "Demultiplexed Name", 300, required=True, max_length=models.Sample.name.type.length, min_length=4, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        DropdownColumn("sample_name", "Sample (Pool) Name", 300, choices=[], required=True),
        TextColumn("barcode_id", "Bardcode ID", 200, required=True, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH, clean_up_fnc=lambda x: str(x).strip().upper()),
    ]

    allowed_barcodes = [f"OB{i}" for i in range(1, 5)]

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return current_step.metadata["mux_type_id"] == MUXType.TENX_ON_CHIP.id

    @classmethod
    def __get_multiplexed_samples(cls, df: pd.DataFrame) -> list[str]:
        return df["sample_name"].unique().tolist()

    def __init__(self, seq_request: models.SeqRequest, uuid: str, previous_form: Optional[MultiStepForm] = None, formdata: dict = {}):
        MultiStepForm.__init__(
            self, workflow=OCMAnnotationForm._workflow_name, step_name=OCMAnnotationForm._step_name,
            uuid=uuid, formdata=formdata, previous_form=previous_form, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.upload_path = "uploads/seq_request"

        self.multiplexed_samples = OCMAnnotationForm.__get_multiplexed_samples(self.tables["library_table"])

        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=OCMAnnotationForm.columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_ocm_reference', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )
        self.spreadsheet.columns["sample_name"].source = self.multiplexed_samples

    def fill_previous_form(self, previous_form: StepFile):
        self.spreadsheet.set_data(previous_form.tables["sample_pooling_table"])

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df
        
        if df.empty:
            self.spreadsheet.add_general_error("Spreadsheet is empty..")
            return False

        def padded_barcode_id(s: str) -> str:
            number = ''.join(filter(str.isdigit, s))
            return f"OB{number}"
        
        df["barcode_id"] = df["barcode_id"].apply(lambda s: padded_barcode_id(s) if pd.notna(s) else None)
        duplicate_annotation = df.duplicated(subset=["sample_name", "barcode_id"], keep=False)

        for i, (idx, row) in enumerate(df.iterrows()):
            if duplicate_annotation[i]:
                self.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue("Sample name and barcode ID combination must be unique."))
                self.spreadsheet.add_error(idx, "barcode_id", DuplicateCellValue("Sample name and barcode ID combination must be unique."))
                continue
            
            if row["barcode_id"] not in OCMAnnotationForm.allowed_barcodes:
                self.spreadsheet.add_error(idx, "barcode_id", InvalidCellValue(f"Barcode ID must be one of {OCMAnnotationForm.allowed_barcodes}."))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        sample_table = self.tables["sample_table"]
        sample_pooling_table = self.tables["sample_pooling_table"]

        pooling_data = {
            "sample_name": [],
            "library_name": [],
            "mux_barcode": [],
            "mux_type_id": [],
            "sample_pool": [],
        }

        sample_data = {"sample_name": []}

        for _, mux_row in self.df.iterrows():
            sample_data["sample_name"].append(mux_row["demux_name"])
            for _, pooling_row in sample_pooling_table[sample_pooling_table["sample_name"] == mux_row["sample_name"]].iterrows():
                pooling_data["sample_name"].append(mux_row["demux_name"])
                pooling_data["library_name"].append(pooling_row["library_name"])
                pooling_data["mux_barcode"].append(mux_row["barcode_id"])
                pooling_data["mux_type_id"].append(MUXType.TENX_ON_CHIP.id)
                pooling_data["sample_pool"].append(mux_row["sample_name"])

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
        self.update_data()

        if FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif KitMappingForm.is_applicable(self):
            next_form = KitMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)

        return next_form.make_response()