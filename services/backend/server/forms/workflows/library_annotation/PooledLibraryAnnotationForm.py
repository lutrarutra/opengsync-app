from fastapi import Depends, Response

from opengsync_db import models, categories as C

from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from ....components.tables import TextColumn
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep

class PooledLibraryAnnotationForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-pooled_library_annotation.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        TextColumn("library_name", "Library Name", 300, required=True, read_only=True),
        TextColumn("pool", "Pool", 300, required=True, max_length=models.Pool.name.type.length, min_length=4),
    ])

    @classmethod
    def is_applicable(cls, workflow: "LibraryAnnotationWorkflow") -> bool:
        return C.SubmissionType.get(workflow.header["submission_type_id"]) == C.SubmissionType.POOLED_LIBRARIES
    
    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.library_table = self.workflow.tables["library_table"]
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        self.spreadsheet.set_data(self.library_table)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: PooledLibraryAnnotationForm = Depends(PooledLibraryAnnotationForm.PreviousStep()),
        ) -> Response:
            df = form.library_table
            form.spreadsheet.set_data(df)
            return form.make_response()
        return route
        

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: PooledLibraryAnnotationForm = Depends(PooledLibraryAnnotationForm.Validate()),
        ) -> Response:
            df = form.spreadsheet.data

            form.library_table["pool"] = None
            
            for _, row in df.iterrows():
                form.library_table.loc[(form.library_table["library_name"] == row["library_name"]), "pool"] = row["pool"]

            form.workflow.tables["library_table"] = form.library_table
            next_form = form.workflow.get_next_step(form)
            return next_form.make_response()
        return route