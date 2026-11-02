import pandas as pd
from fastapi import Depends, Response

from opengsync_db import categories as C

from ....utils import parsing
from ....components import inputs
from ....components.tables import TextColumn
from ...HTMXForm import RouteFunc, htmx_route
from ...common import protocol_columns
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow, LibraryAnnotationWorkflowStep


class LibraryProtocolAnnotationForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-library_protocol_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            TextColumn("library_name", "Library", 400, required=True, read_only=True),
            # Optional: left empty if the protocol is not listed
            protocol_columns.protocol_column("protocol_id", "Protocol", 600),
        ],
        allow_new_rows=False,
    )

    @classmethod
    def is_applicable(cls, workflow: "LibraryAnnotationWorkflow") -> bool:
        # Raw samples are prepared by the facility, which chooses the protocol
        return workflow.header["submission_type_id"] in [C.SubmissionType.POOLED_LIBRARIES.id, C.SubmissionType.UNPOOLED_LIBRARIES.id]

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        self.library_table = workflow.tables["library_table"]
        if "protocol_id" not in self.library_table.columns:
            self.library_table["protocol_id"] = None
        self.library_table["protocol_id"] = self.library_table["protocol_id"].astype(pd.Int64Dtype())
        self.spreadsheet.set_data(self.library_table[["library_name", "protocol_id"]])

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: LibraryProtocolAnnotationForm = Depends(LibraryProtocolAnnotationForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: LibraryProtocolAnnotationForm = Depends(LibraryProtocolAnnotationForm.Validate()),
        ) -> Response:
            df = form.spreadsheet.data
            form.assert_valid()

            # Mapped by name, so rows that do not match a library are ignored
            form.library_table["protocol_id"] = parsing.map_columns(form.library_table, df, "library_name", "protocol_id").astype(pd.Int64Dtype())
            form.workflow.tables["library_table"] = form.library_table
            return form.workflow.get_next_step(form).make_response()
        return route
