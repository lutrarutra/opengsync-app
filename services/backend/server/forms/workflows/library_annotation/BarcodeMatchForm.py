from fastapi import Depends, Response

from opengsync_db import categories as C

from ...common.BarcodeMatchMixin import BarcodeMatchMixin
from ...HTMXForm import RouteFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow, LibraryAnnotationWorkflowStep


class BarcodeMatchForm(BarcodeMatchMixin, LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-barcode-match.html"

    i7_kit = BarcodeMatchMixin.make_kit_field("i7")
    i5_kit = BarcodeMatchMixin.make_kit_field("i5")
    i7_option = BarcodeMatchMixin.make_option_field("i7")
    i5_option = BarcodeMatchMixin.make_option_field("i5")
    i7_primer = BarcodeMatchMixin.make_primer_field("i7")
    i5_primer = BarcodeMatchMixin.make_primer_field("i5")

    @classmethod
    def is_applicable(cls, workflow: LibraryAnnotationWorkflow) -> bool:
        df = workflow.tables["barcode_table"]
        df = df[(df["index_type_id"] != C.IndexType.TENX_ATAC_INDEX.id) & ((df["index_well"] != "del") | (df["index_well"].isna()))]
        return (not df.empty) and bool(df["kit_i7"].isna().all() and df["kit_i5"].isna().all())

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
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
            form: BarcodeMatchForm = Depends(BarcodeMatchForm.Init()),
        ) -> Response:
            form.fill_barcode_match(form.workflow.metadata.get("barcode_match_form", {}))
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: BarcodeMatchForm = Depends(BarcodeMatchForm.Validate()),
        ) -> Response:
            form.validate_barcode_match()
            form.assert_valid()

            form.workflow.tables["barcode_table"] = form.apply_barcode_match()
            form.workflow.metadata["barcode_match_form"] = form.barcode_match_metadata()

            if form.i7_primer.data:
                form.workflow.add_comment(context="i7_primer", text=form.i7_primer.data)
            if form.i5_primer.data:
                form.workflow.add_comment(context="i5_primer", text=form.i5_primer.data)

            return form.workflow.get_next_step(form).make_response()
        return route
