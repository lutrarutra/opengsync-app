from fastapi import Depends, Response

from ...common.BarcodeMatchMixin import BarcodeMatchMixin
from ...HTMXForm import RouteFunc, htmx_route
from ..HTMXWorkflow import HTMXWorkflow
from .ReindexWorkflow import ReindexWorkflowStep, ReindexWorkflow


class BarcodeMatchForm(BarcodeMatchMixin, ReindexWorkflowStep):
    template_path = "workflows/reindex/barcode-match.html"

    i7_kit = BarcodeMatchMixin.make_kit_field("i7")
    i5_kit = BarcodeMatchMixin.make_kit_field("i5")
    i7_option = BarcodeMatchMixin.make_option_field("i7")
    i5_option = BarcodeMatchMixin.make_option_field("i5")
    i7_primer = BarcodeMatchMixin.make_primer_field("i7")
    i5_primer = BarcodeMatchMixin.make_primer_field("i5")

    @classmethod
    def is_applicable(cls, workflow: "HTMXWorkflow") -> bool:
        barcode_table = workflow.tables.get("barcode_table")
        if barcode_table is None or barcode_table.empty:
            return False
        if "index_well" in barcode_table.columns:
            barcode_table = barcode_table[
                (barcode_table["index_well"] != "del") | barcode_table["index_well"].isna()
            ]
        if barcode_table.empty:
            return False
        return bool(barcode_table["kit_i7"].isna().all() and barcode_table["kit_i5"].isna().all())

    def __init__(self, workflow: ReindexWorkflow) -> None:
        super().__init__(workflow)
        # Work on the table as entered in the previous step: after 'Back', barcode_table is
        # already matched/reverse-complemented and must not be transformed a second time.
        if (input_table := workflow.tables.get("barcode_match_input_table")) is None:
            input_table = workflow.tables["barcode_table"]
            workflow.tables["barcode_match_input_table"] = input_table.copy()
        self.init_barcode_match(input_table)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "BarcodeMatchForm" = Depends(BarcodeMatchForm.Init()),
        ) -> Response:
            form.fill_barcode_match(form.workflow.metadata.get("barcode_match_form", {}))
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "BarcodeMatchForm" = Depends(BarcodeMatchForm.Validate()),
        ) -> Response:
            form.validate_barcode_match()
            form.assert_valid()

            form.workflow.tables["barcode_table"] = form.apply_barcode_match()
            form.workflow.metadata["barcode_match_form"] = form.barcode_match_metadata()
            return form.workflow.get_next_step(form).make_response()
        return route
