from fastapi import Depends, Response
import pandas as pd

from opengsync_db import models, categories as C

from ....utils import barcodes
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from ..HTMXWorkflow import HTMXWorkflow
from .ReindexWorkflow import ReindexWorkflowStep, ReindexWorkflow
from .CompleteReindexForm import CompleteReindexForm

class BarcodeMatchForm(ReindexWorkflowStep):
    template_path = "workflows/reindex/barcode-match.html"

    i7_kit = inputs.selectable.SelectableInputField("i7 Kit", options=[(0, "Custom")], required=True)
    i5_kit = inputs.selectable.SelectableInputField("i5 Kit", options=[(0, "Custom")], required=False)
    i7_option = inputs.selectable.SelectableInputField(
        "i7 Orientation",
        options=[(1, "Forward"), (2, "Reverse Complement"), (3, "I don't know")],
        required=False,
    )
    i5_option = inputs.selectable.SelectableInputField(
        "i5 Orientation",
        options=[(1, "Forward"), (2, "Reverse Complement"), (3, "I don't know")],
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

    def __init__(self, workflow: ReindexWorkflow) -> None:
        super().__init__(workflow)
        self.barcode_table = workflow.tables["barcode_table"]
        self.index_type = barcodes.check_index_type(self.barcode_table)
        self._context["index_type"] = self.index_type

    def prepare(self) -> None:
        from ....core.context import ctx

        session = ctx.session

        df = self.barcode_table.copy()
        df["rc_sequence_i7"] = df["sequence_i7"].apply(
            lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None
        )
        df["rc_sequence_i5"] = df["sequence_i5"].apply(
            lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None
        )

        sequences_i7 = [s for s in df["sequence_i7"].tolist() if pd.notna(s)]
        sequences_i5 = [s for s in df["sequence_i5"].tolist() if pd.notna(s)]
        rc_sequences_i7 = [s for s in df["rc_sequence_i7"].tolist() if pd.notna(s)]
        rc_sequences_i5 = [s for s in df["rc_sequence_i5"].tolist() if pd.notna(s)]

        kits_i7 = session.pd.match_barcodes_to_kit(sequences_i7, C.BarcodeType.INDEX_I7)
        kits_i5 = session.pd.match_barcodes_to_kit(sequences_i5, C.BarcodeType.INDEX_I5)
        kits_rc_i7 = session.pd.match_barcodes_to_kit(rc_sequences_i7, C.BarcodeType.INDEX_I7)
        kits_rc_i5 = session.pd.match_barcodes_to_kit(rc_sequences_i5, C.BarcodeType.INDEX_I5)

        kit_i7s: list[tuple[int, str]] = []
        for _, row in kits_i7.iterrows():
            kit_i7s.append((row["kit_id"], f'[{row["kit_identifier"]}] {row["kit_name"]}'))
        for _, row in kits_rc_i7.iterrows():
            kit_i7s.append((row["kit_id"], f'[{row["kit_identifier"]}] {row["kit_name"]}' + " (Reverse Complement)"))

        kit_i5s: list[tuple[int, str]] = []
        for _, row in kits_i5.iterrows():
            kit_i5s.append((row["kit_id"], f'[{row["kit_identifier"]}] {row["kit_name"]}'))
        for _, row in kits_rc_i5.iterrows():
            kit_i5s.append((row["kit_id"], f'[{row["kit_identifier"]}] {row["kit_name"]}' + " (Reverse Complement)"))

        self.i7_kit.set_options([(0, "Custom")] + kit_i7s)
        self.i5_kit.set_options([(0, "Custom")] + kit_i5s)

        self._context["kits"] = list(set(kit_i7s + kit_i5s))

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "BarcodeMatchForm" = Depends(BarcodeMatchForm.Init()),
        ) -> Response:
            form.prepare()
            form.i7_kit.data = form.workflow.metadata["i7_kit"]
            form.i5_kit.data = form.workflow.metadata["i5_kit"]
            form.i7_option.data = form.workflow.metadata["i7_option"]
            form.i5_option.data = form.workflow.metadata["i5_option"]
            form.i7_primer.data = form.workflow.metadata["i7_primer"]
            form.i5_primer.data = form.workflow.metadata["i5_primer"]
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "BarcodeMatchForm" = Depends(BarcodeMatchForm.Validate()),
        ) -> Response:
            form.workflow.metadata["i7_kit"] = form.i7_kit.data
            form.workflow.metadata["i5_kit"] = form.i5_kit.data
            form.workflow.metadata["i7_option"] = form.i7_option.data
            form.workflow.metadata["i5_option"] = form.i5_option.data
            form.workflow.metadata["i7_primer"] = form.i7_primer.data
            form.workflow.metadata["i5_primer"] = form.i5_primer.data
            return form.workflow.get_next_step(form).make_response()
        return route