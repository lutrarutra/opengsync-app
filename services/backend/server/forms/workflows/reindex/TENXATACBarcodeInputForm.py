from fastapi import Depends, Response

from opengsync_db import models, queries as Q, categories as C

from ....core import context
from ....components import inputs
from ....components.tables.spreadsheet import DBObjectColumn, TextColumn, CategoricalDropDown
from ...HTMXForm import RouteFunc, htmx_route
from .ReindexWorkflow import ReindexWorkflowStep, ReindexWorkflow
from .BarcodeInputForm import assert_libraries_listed


class TENXATACBarcodeInputForm(ReindexWorkflowStep):
    template_path = "workflows/reindex/barcode-input.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            DBObjectColumn(
                columns=("library_id", "library_name"),
                types=(int, str),
                label="Library",
                width=300,
                categories={},
                required=True,
            ),
            TextColumn("index_well", "Index Well", 100, max_length=8, required=False),
            CategoricalDropDown("kit", "Kit", 200, categories=lambda: {
                kit.identifier: f"[{kit.identifier}] {kit.name}"
                for kit in context.ctx.session.get_all(
                    Q.index_kit.select(type=C.IndexType.TENX_ATAC_INDEX),
                    order_by=models.IndexKit.name.desc(),
                    limit=None,
                )
            }, required=False),
            TextColumn("name", "Name", 150, required=False),
            TextColumn("sequence_1", "Sequence 1", 180, required=True),
            TextColumn("sequence_2", "Sequence 2", 180, required=True),
            TextColumn("sequence_3", "Sequence 3", 180, required=True),
            TextColumn("sequence_4", "Sequence 4", 180, required=True),
        ],
        allow_new_rows=True,
    )

    @classmethod
    def is_applicable(cls, workflow: "ReindexWorkflow") -> bool:
        library_table = workflow.tables["library_table"]
        return bool((library_table["library_type"] == C.LibraryType.TENX_SC_ATAC).any())

    def __init__(self, workflow: "ReindexWorkflow") -> None:
        super().__init__(workflow=workflow)
        self.barcode_table = self.workflow.tables["tenx_atac_barcode_table"]
        self.library_table = self.workflow.tables["library_table"]

        self.spreadsheet.columns["Library"].set_categories({
            row["library_id"]: f"{row['library_name']} [{row['library_id']}]"
            for _, row in self.library_table.iterrows()
            if row["library_type"] == C.LibraryType.TENX_SC_ATAC
        })

        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url, df=self.barcode_table)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "TENXATACBarcodeInputForm" = Depends(TENXATACBarcodeInputForm.Init()),
        ) -> Response:
            barcode_table = form.workflow.tables["tenx_atac_barcode_table"]
            form.spreadsheet.set_data(barcode_table)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "TENXATACBarcodeInputForm" = Depends(TENXATACBarcodeInputForm.Validate()),
        ) -> Response:
            assert_libraries_listed(form, form.spreadsheet.data, atac=True)
            form.assert_valid()
            form.workflow.tables["tenx_atac_barcode_table"] = form.spreadsheet.data
            next_step = form.workflow.get_next_step(form)
            return next_step.make_response()
        return route