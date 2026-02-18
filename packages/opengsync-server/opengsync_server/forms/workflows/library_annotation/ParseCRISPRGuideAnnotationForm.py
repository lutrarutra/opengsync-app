from flask import Response, url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType

from .... import logger # noqa
from ....tools.spread_sheet_components import TextColumn
from ...SpreadsheetInput import SpreadsheetInput
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow


class ParseCRISPRGuideAnnotationForm(LibraryAnnotationWorkflow):
    _template_path = "workflows/library_annotation/sas-parse_crispr_guide_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "parse_crispr_guide_annotation"

    columns: list = [
        TextColumn("guide_name", "Guide Name", 150, max_length=64, required=True, unique=True),
        TextColumn("target_gene", "Target Gene", 150, max_length=64, required=True),
        TextColumn("prefix", "Prefix", 250, max_length=256, required=True),
        TextColumn("guide_sequence", "Guide Sequence", 200, max_length=256, required=True),
        TextColumn("suffix", "Suffix", 250, max_length=256, required=True),
    ]

    @staticmethod
    def is_applicable(current_step: LibraryAnnotationWorkflow) -> bool:
        return bool(current_step.tables["library_table"]["library_type_id"].isin([LibraryType.PARSE_SC_CRISPR.id]).any())

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        LibraryAnnotationWorkflow.__init__(self, seq_request=seq_request, step_name=ParseCRISPRGuideAnnotationForm._step_name, formdata=formdata, uuid=uuid)

        self.library_table = self.tables["library_table"]        
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=ParseCRISPRGuideAnnotationForm.columns, csrf_token=self._csrf_token,
            post_url=url_for('library_annotation_workflow.parse_parse_crispr_guide_annotation', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )
    
    def fill_previous_form(self):
        crispr_guide_table = self.tables["crispr_guide_table"]
        self.spreadsheet.set_data(crispr_guide_table)

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df
            
        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.tables["crispr_guide_table"] = self.df
        return self.get_next_step().make_response()
 
