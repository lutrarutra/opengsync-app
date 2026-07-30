from fastapi import Depends, Response

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, responses
from ....components import inputs
from ....components.tables.spreadsheet import TextColumn, CategoricalDropDown
from ....components.tables import IntegerColumn
from ...HTMXForm import RouteFunc, htmx_route
from ..HTMXWorkflow import HTMXWorkflow
from .ReindexWorkflow import ReindexWorkflowStep


class TENXATACBarcodeInputForm(ReindexWorkflowStep):
    template_path = "workflows/reindex/barcode-input.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
            TextColumn("library_name", "Library Name", 250, required=True, read_only=True),
            TextColumn("index_well", "Index Well", 100, max_length=8, required=False),
            CategoricalDropDown("kit", "Kit", 200, categories={}, required=False),
            TextColumn("name", "Name", 150, required=False),
            TextColumn("sequence_1", "Sequence 1", 180, required=True),
            TextColumn("sequence_2", "Sequence 2", 180, required=True),
            TextColumn("sequence_3", "Sequence 3", 180, required=True),
            TextColumn("sequence_4", "Sequence 4", 180, required=True),
        ],
        allow_new_rows=False,
    )

    @classmethod
    def is_applicable(cls, workflow: "HTMXWorkflow") -> bool:
        library_table = workflow.tables.get("library_table")
        if library_table is None or "library_type_id" not in library_table.columns:
            return False
        return bool((library_table["library_type_id"] == C.LibraryType.TENX_SC_ATAC.id).any())

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "TENXATACBarcodeInputForm" = Depends(TENXATACBarcodeInputForm.Validate()),
        ) -> Response:
            form.workflow.tables["tenx_atac_barcode_table"] = form.spreadsheet.data
            next_step = form.workflow.get_next_step(form)
            return next_step.make_response()
        return route