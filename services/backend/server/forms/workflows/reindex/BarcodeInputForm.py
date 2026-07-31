from fastapi import Depends, Response

from opengsync_db import models, queries as Q, categories as C

from ....core import dependencies, context
from ....components.tables import DBObjectColumn
from ....components.tables.spreadsheet import TextColumn, CategoricalDropDown
from ...HTMXForm import RouteFunc, htmx_route
from ...common.BarcodeInputMixin import BarcodeInputMixin
from .ReindexWorkflow import ReindexWorkflowStep, ReindexWorkflow
from .BarcodeMatchForm import BarcodeMatchForm

class BarcodeInputForm(BarcodeInputMixin, ReindexWorkflowStep):
    template_path = "workflows/reindex/barcode-input.html"

    spreadsheet = BarcodeInputMixin.make_spreadsheet(
        DBObjectColumn(
            columns=("library_id", "library_name"),
            label="Library",
            width=300,
            categories={},
            required=True,
        ),
    )

    @classmethod
    def is_applicable(cls, workflow: "ReindexWorkflow") -> bool:
        library_table = workflow.tables["library_table"]
        return bool((library_table["library_type"] != C.LibraryType.TENX_SC_ATAC.id).any())

    def __init__(self, workflow: "ReindexWorkflow") -> None:
        super().__init__(workflow=workflow)
        self.barcode_table = self.workflow.tables["barcode_table"]

        self.spreadsheet.columns["Library"].set_categories({
            row["library_id"]: f"{row['library_name']} [{row['library_id']}]"
            for _, row in self.barcode_table.iterrows()
            if row["library_type"] != C.LibraryType.TENX_SC_ATAC.id
        })

        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url, df=self.barcode_table)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "BarcodeInputForm" = Depends(BarcodeInputForm.Init()),
        ) -> Response:
            barcode_table = form.workflow.tables["barcode_table"]
            form.spreadsheet.set_data(barcode_table)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "BarcodeInputForm" = Depends(BarcodeInputForm.Validate()),
        ) -> Response:
            df = form.validate_barcode_input()
            form.workflow.tables["barcode_table"] = df
            return form.workflow.get_next_step(form).make_response()
        return route