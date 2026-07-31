from fastapi import Depends, Response

from opengsync_db import models, categories as C, queries as Q, SyncSession

from ....core import dependencies
from ....components.tables import DropdownColumn
from ...HTMXForm import RouteFunc, htmx_route
from ...common.BarcodeInputMixin import BarcodeInputMixin
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow, LibraryAnnotationWorkflowStep


class BarcodeInputForm(BarcodeInputMixin, LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-barcode-input.html"

    spreadsheet = BarcodeInputMixin.make_spreadsheet(
        DropdownColumn("library_name", "Library Name", 250, choices=[]),
    )

    @classmethod
    def is_applicable(cls, workflow: LibraryAnnotationWorkflow) -> bool:
        return bool((workflow.tables["library_table"]["library_type_id"] != C.LibraryType.TENX_SC_ATAC.id).any())

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.library_table = workflow.tables["library_table"]
        self.spreadsheet.columns["library_name"].set_choices(
            lambda: [
                str(name)
                for name in self.library_table["library_name"].dropna().unique()
            ]
        )
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        from ....core.context import ctx
        i7_kit_mapping = {
            kit.identifier: f"[{kit.identifier}] {kit.name}"
            for kit in ctx.session.get_all(
                Q.index_kit.select(type_in=[
                    C.IndexType.DUAL_INDEX,
                    C.IndexType.SINGLE_INDEX_I7,
                    C.IndexType.COMBINATORIAL_DUAL_INDEX,
                ]),
                order_by=models.IndexKit.name.desc(),
                limit=None,
            )
        }
        i5_kit_mapping = {
            kit.identifier: f"[{kit.identifier}] {kit.name}"
            for kit in ctx.session.get_all(
                Q.index_kit.select(type_in=[
                    C.IndexType.DUAL_INDEX,
                    C.IndexType.COMBINATORIAL_DUAL_INDEX,
                ]),
                order_by=models.IndexKit.name.desc(),
                limit=None,
            )
        }
        self.spreadsheet.columns["kit_i7"].set_categories(i7_kit_mapping)
        self.spreadsheet.columns["kit_i5"].set_categories(i5_kit_mapping)

        barcode_table = self.library_table[
            self.library_table["library_type_id"] != C.LibraryType.TENX_SC_ATAC.id
        ].copy()
        self.spreadsheet.set_data(barcode_table)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: BarcodeInputForm = Depends(BarcodeInputForm.Init()),
        ) -> Response:
            barcode_table = form.workflow.tables["barcode_table"]
            barcode_table = barcode_table[barcode_table["index_type_id"] != C.IndexType.TENX_ATAC_INDEX.id].copy()
            form.spreadsheet.set_data(barcode_table)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: BarcodeInputForm = Depends(BarcodeInputForm.Validate()),
        ) -> Response:
            df = form.validate_barcode_input()
            form.workflow.tables["barcode_table"] = df
            return form.workflow.get_next_step(form).make_response()
        return route
