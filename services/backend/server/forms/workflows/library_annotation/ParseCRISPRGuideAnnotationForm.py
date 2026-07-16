from fastapi import Depends, Response

from opengsync_db import categories as C

from ....core import responses
from ....components import inputs
from ....components.tables import TextColumn
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep


class ParseCRISPRGuideAnnotationForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-parse_crispr_guide_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        TextColumn("guide_name", "Guide Name", 150, max_length=64, required=True, unique=True),
        TextColumn("target_gene", "Target Gene", 150, max_length=64, required=True),
        TextColumn("prefix", "Prefix", 250, max_length=256, required=True),
        TextColumn("guide_sequence", "Guide Sequence", 200, max_length=256, required=True),
        TextColumn("suffix", "Suffix", 250, max_length=256, required=True),
    ])

    @classmethod
    def is_applicable(cls, workflow: "LibraryAnnotationWorkflow") -> bool:
        return bool(workflow.tables["library_table"]["library_type_id"].isin([C.LibraryType.PARSE_SC_CRISPR.id]).any())
    
    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.library_table = workflow.tables["library_table"]
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: ParseCRISPRGuideAnnotationForm = Depends(ParseCRISPRGuideAnnotationForm.Init()),
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
        ) -> Response:
            crispr_guide_table = workflow.tables["crispr_guide_table"]
            form.spreadsheet.set_data(crispr_guide_table)
            return form.make_response()
        return route
    
    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
            form: ParseCRISPRGuideAnnotationForm = Depends(ParseCRISPRGuideAnnotationForm.Validate()),
        ) -> Response:
            df = form.spreadsheet.data
            workflow.tables["crispr_guide_table"] = df
            return workflow.get_next_step(form).make_response()
        return route


