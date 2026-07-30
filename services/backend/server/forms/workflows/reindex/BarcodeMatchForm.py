from fastapi import Depends, Response

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, responses
from ....core.utils import barcodes
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from ..HTMXWorkflow import HTMXWorkflow
from .ReindexWorkflow import ReindexWorkflowStep


class BarcodeMatchForm(ReindexWorkflowStep):
    template_path = "workflows/reindex/barcode-match.html"

    i7_kit = inputs.selectable.SelectableInputField("i7 Kit", options=[(-1, "Select Kit"), (0, "Custom")], required=True)
    i5_kit = inputs.selectable.SelectableInputField("i5 Kit", options=[(-1, "Select Kit"), (0, "Custom")], required=False)
    i7_option = inputs.selectable.SelectableInputField(
        "i7 Orientation",
        options=[("forward", "Forward"), ("rc", "Reverse Complement"), ("idk", "I don't know")],
        required=False,
    )
    i5_option = inputs.selectable.SelectableInputField(
        "i5 Orientation",
        options=[("forward", "Forward"), ("rc", "Reverse Complement"), ("idk", "I don't know")],
        required=False,
    )
    i7_primer = inputs.string.StringInputField("i7 Primer Sequence", required=False, max_length=255)
    i5_primer = inputs.string.StringInputField("i5 Primer Sequence", required=False, max_length=255)

    @classmethod
    def is_applicable(cls, workflow: "HTMXWorkflow") -> bool:
        barcode_table = workflow.tables.get("barcode_table")
        if barcode_table is None or barcode_table.empty:
            return False
        return bool(barcode_table["kit_i7"].isna().all() and barcode_table["kit_i5"].isna().all())

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "BarcodeMatchForm" = Depends(BarcodeMatchForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            form.workflow.metadata["i7_kit"] = form.i7_kit.data
            form.workflow.metadata["i5_kit"] = form.i5_kit.data
            form.workflow.metadata["i7_option"] = form.i7_option.data
            form.workflow.metadata["i5_option"] = form.i5_option.data
            form.workflow.metadata["i7_primer"] = form.i7_primer.data
            form.workflow.metadata["i5_primer"] = form.i5_primer.data

            next_step = form.workflow.get_next_step(form)
            return next_step.make_response()
        return route