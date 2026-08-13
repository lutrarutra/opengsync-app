from fastapi import Depends, Response
from pydantic import BaseModel

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, responses
from ....utils import parsing
from ....components import inputs
from ....components.tables import IntegerColumn, TextColumn, CategoricalDropDown, DropdownColumn
from ...HTMXForm import RouteFunc, htmx_route
from .RelibWorkflow import RelibWorkflowStep, RelibWorkflow


class LibraryEditTableForm(RelibWorkflowStep):
    template_path = "workflows/relib/table_form.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
            TextColumn(
                "sample_name", "Sample Name", 250, required=True,
                max_length=models.Library.sample_name.type.length, min_length=4,
                validation_fnc=lambda x: parsing.check_string(x, allowed_special_characters=["_", "."]),
            ),
            TextColumn(
                "library_name", "Library Name", 250, required=True,
                max_length=models.Library.name.type.length, min_length=4,
                validation_fnc=lambda x: parsing.check_string(x, allowed_special_characters=["_", "."]),
            ),
            CategoricalDropDown("library_type_id", "Library Type", 300, categories=dict(C.LibraryType.as_selectable()), required=True),
            CategoricalDropDown("genome_id", "Genome", 300, categories=dict(C.GenomeRef.as_selectable()), required=True),
            CategoricalDropDown("service_type_id", "Assay/Service Type", 300, categories=dict(C.ServiceType.as_selectable()), required=True),
            DropdownColumn("nuclei_isolation", "Nuclei", 100, choices=["Yes", "No"], required=True),
        ],
        allow_new_rows=False,
    )

    def __init__(self, workflow: RelibWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.spreadsheet.configure(
            csrf_token=self.csrf_token_value,
            post_url=self.post_url,
            df=self.workflow.tables["library_table"],
        )

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "LibraryEditTableForm" = Depends(LibraryEditTableForm.Init()),
        ) -> Response:
            form.spreadsheet.set_data(form.workflow.tables["library_table"])
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "LibraryEditTableForm" = Depends(LibraryEditTableForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            class RowSchema(BaseModel):
                library_id: int
                sample_name: str
                library_name: str
                library_type_id: int
                genome_id: int
                service_type_id: int
                nuclei_isolation: str

            for _, row in parsing.safe_iter(form.spreadsheet.data, RowSchema):
                library = session.get_one(Q.library.select(id=row.library_id))
                library.name = row.library_name
                library.sample_name = row.sample_name
                library.type = C.LibraryType.get(row.library_type_id)
                library.genome_ref = C.GenomeRef.get(row.genome_id)
                library.nuclei_isolation = row.nuclei_isolation == "Yes"
                library.service_type = C.ServiceType.get(row.service_type_id)

            next_url = responses.url_for("dashboard")
            if form.workflow.seq_request_id is not None:
                next_url = responses.url_for("seq_request_page", seq_request_id=form.workflow.seq_request_id)
            elif form.workflow.lab_prep_id is not None:
                next_url = responses.url_for("lab_prep_page", lab_prep_id=form.workflow.lab_prep_id)

            form.workflow.complete()
            return responses.htmx_response(
                redirect=next_url,
                flash=responses.flash("Changes Saved!", "success"),
            )
        return route
