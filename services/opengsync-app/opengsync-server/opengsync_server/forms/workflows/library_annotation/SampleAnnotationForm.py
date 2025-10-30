from typing import Any, Mapping
import pandas as pd

from flask import Response, url_for
from wtforms import SelectField, BooleanField

from opengsync_db import models
from opengsync_db.categories import GenomeRef

from .... import logger, db
from ....tools import utils
from ....tools.spread_sheet_components import TextColumn, CategoricalDropDown
from ...MultiStepForm import MultiStepForm, StepFile
from ...SpreadsheetInput import SpreadsheetInput
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm

class SampleAnnotationForm(MultiStepForm):
    
    _step_name = "sample_annotation"
    _workflow_name = "library_annotation"
    _template_path = "workflows/library_annotation/sas-sample_annotation.html"

    columns = [
        TextColumn("sample_name", "Sample Name", 300, required=True, max_length=models.Sample.name.type.length, min_length=4, clean_up_fnc=utils.make_alpha_numeric, validation_fnc=utils.check_string, unique=True),
        CategoricalDropDown("genome_id", "Genome", 300, categories=dict(GenomeRef.as_selectable()), required=True),
    ]

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, uuid=uuid, workflow=SampleAnnotationForm._workflow_name,
            step_name=SampleAnnotationForm._step_name,
            formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.spreadsheet = SpreadsheetInput(
            columns=SampleAnnotationForm.columns, csrf_token=self._csrf_token,
            post_url=url_for('library_annotation_workflow.parse_sample_annotation_form', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )
        self._context["project_id"] = self.metadata.get("project_id")

    def fill_previous_form(self, previous_form: StepFile):
        self.spreadsheet.set_data(previous_form.tables["sample_table"])

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        self.df = self.spreadsheet.df

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.df["sample_id"] = None

        if (project_id := self.metadata.get("project_id")) is not None:
            if (project := db.projects.get(project_id)) is None:
                logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
                raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
            
            for sample in project.samples:
                self.df.loc[self.df["sample_name"] == sample.name, "sample_id"] = sample.id

        self.add_table("sample_table", self.df)
        self.update_data()

        next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        return next_form.make_response()
