import pandas as pd
from fastapi import Depends, Response
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, responses
from ....components import inputs
from ....components.tables.spreadsheet import TextColumn, CategoricalDropDown, IntegerColumn
from ...HTMXForm import RouteFunc, htmx_route
from .ReindexWorkflow import ReindexWorkflowStep


class BarcodeInputForm(ReindexWorkflowStep):
    template_path = "workflows/reindex/barcode-input.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
            TextColumn("library_name", "Library Name", 250, required=True, read_only=True),
            TextColumn("index_well", "Index Well", 100, max_length=8, required=False),
            CategoricalDropDown("kit_i7", "i7 Kit", 200, categories={}, required=False),
            TextColumn("name_i7", "i7 Name", 150, required=False),
            TextColumn("sequence_i7", "i7 Sequence", 180, required=False),
            CategoricalDropDown("kit_i5", "i5 Kit", 200, categories={}, required=False),
            TextColumn("name_i5", "i5 Name", 150, required=False),
            TextColumn("sequence_i5", "i5 Sequence", 180, required=False),
        ],
        allow_new_rows=False,
    )

    def __init__(self, workflow: "ReindexWorkflow") -> None:
        super().__init__(workflow=workflow)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "BarcodeInputForm" = Depends(BarcodeInputForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "BarcodeInputForm" = Depends(BarcodeInputForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            df = form.spreadsheet.data
            form.workflow.tables["barcode_table"] = df
            next_step = form.workflow.get_next_step(form)
            return next_step.make_response()
        return route