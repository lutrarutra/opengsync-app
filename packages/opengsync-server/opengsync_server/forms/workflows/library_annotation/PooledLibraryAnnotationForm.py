from flask import Response, url_for

from opengsync_db import models
from opengsync_db.categories import SubmissionType

from .... import logger, db
from ....tools.spread_sheet_components import TextColumn
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput
from .PoolMappingForm import PoolMappingForm


class PooledLibraryAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-pooled_library_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "pooled_library_annotation"

    columns: list = [
        TextColumn("library_name", "Library Name", 300, required=True, read_only=True),
        TextColumn("pool", "Pool", 300, required=True, max_length=models.Pool.name.type.length, min_length=4),
    ]

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return current_step.seq_request.submission_type_id == SubmissionType.POOLED_LIBRARIES.id

    def __init__(
        self, seq_request: models.SeqRequest, uuid: str,
        formdata: dict | None = None
    ):
        MultiStepForm.__init__(
            self, uuid=uuid, workflow=PooledLibraryAnnotationForm._workflow_name,
            step_name=PooledLibraryAnnotationForm._step_name,
            formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.library_table = self.tables["library_table"]
        
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=PooledLibraryAnnotationForm.columns, csrf_token=self._csrf_token,
            post_url=url_for('library_annotation_workflow.parse_pooled_library_annotation_form', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=False, df=self.library_table
        )

    def fill_previous_form(self):
        df = self.tables["library_table"]
        self.spreadsheet.set_data(df)

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False

        if len(self.spreadsheet._errors) > 0:
            return False

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.library_table["pool"] = None
        
        for _, row in self.spreadsheet.df.iterrows():
            self.library_table.loc[(self.library_table["library_name"] == row["library_name"]), "pool"] = row["pool"]
        
        self.tables["library_table"] = self.library_table
        self.step()
        next_form = PoolMappingForm(seq_request=self.seq_request, uuid=self.uuid)
        return next_form.make_response()

        