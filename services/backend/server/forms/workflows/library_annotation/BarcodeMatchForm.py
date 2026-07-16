import pandas as pd
from fastapi import Depends, Response

from opengsync_db import models, categories as C, queries as Q

from ....core import exceptions as exc
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep


def _check_index_type(barcode_table: pd.DataFrame) -> C.IndexType | None:
    if (barcode_table["index_type_id"] == C.IndexType.DUAL_INDEX.id).all():
        return C.IndexType.DUAL_INDEX
    elif (barcode_table["index_type_id"] == C.IndexType.SINGLE_INDEX_I7.id).all():
        return C.IndexType.SINGLE_INDEX_I7
    elif (barcode_table["index_type_id"] == C.IndexType.COMBINATORIAL_DUAL_INDEX.id).all():
        return C.IndexType.COMBINATORIAL_DUAL_INDEX
    elif (barcode_table["index_type_id"] == C.IndexType.TENX_ATAC_INDEX.id).all():
        return C.IndexType.TENX_ATAC_INDEX
    return None


class BarcodeMatchForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-barcode-match.html"

    i7_kit = inputs.selectable.SelectableInputField("i7 Kit", [(0, "Custom")], required=False, default=-1)
    i5_kit = inputs.selectable.SelectableInputField("i5 Kit", [(0, "Custom")], required=False, default=-1)
    i7_option = inputs.string.StringInputField("Index i7 was not found in the database. Please select how to proceed:", required=False)
    i5_option = inputs.string.StringInputField("Index i5 was not found in the database. Please select how to proceed:", required=False)
    i7_primer = inputs.string.TextAreaInputField("i7 Primer Sequence", required=False, placeholder="Required if using custom kit")
    i5_primer = inputs.string.TextAreaInputField("i5 Primer Sequence", required=False, placeholder="Required if using custom kit")

    @classmethod
    def is_applicable(cls, workflow: LibraryAnnotationWorkflow) -> bool:
        df = workflow.tables["barcode_table"]
        df = df[(df["index_well"] != "del") | (df["index_well"].isna())]
        return (not df.empty) and bool(
            df["kit_i7"].isna().all() and df["kit_i5"].isna().all()
        )

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.barcode_table = workflow.tables["barcode_table"]
        self.index_type = _check_index_type(self.barcode_table)
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

        self.i7_kit.options = [(-1, "Select Kit"), (0, "Custom")] + kit_i7s
        self.i5_kit.options = [(-1, "Select Kit"), (0, "Custom")] + kit_i5s
        self.i7_kit._mapping = dict(self.i7_kit.options)
        self.i5_kit._mapping = dict(self.i5_kit.options)

        self._context["kits"] = list(set(kit_i7s + kit_i5s))

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Previous(cls.__name__)),
        ) -> Response:
            form = BarcodeMatchForm(workflow=workflow)
            d = form.workflow.metadata.get("barcode_match_form", {})
            form.i7_kit.data = d.get("i7_kit", -1)
            form.i5_kit.data = d.get("i5_kit", -1)
            form.i7_option.data = d.get("i7_option")
            form.i5_option.data = d.get("i5_option")
            form.i7_primer.data = d.get("i7_primer")
            form.i5_primer.data = d.get("i5_primer")
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: BarcodeMatchForm = Depends(BarcodeMatchForm.Validate()),
        ) -> Response:
            workflow = form.workflow

            if form.i7_kit.data == -1:
                form.i7_kit.errors.append("Please select an i7 kit or choose Custom.")
            if form.i5_kit.data == -1 and form.index_type in [C.IndexType.DUAL_INDEX, C.IndexType.COMBINATORIAL_DUAL_INDEX]:
                form.i5_kit.errors.append("Please select an i5 kit or choose Custom.")

            if form.i7_kit.data == 0 and not form.i7_option.data:
                form.i7_option.errors.append("Please select how to proceed with the i7 index.")
            if form.i7_kit.data == 0 and not form.i7_primer.data:
                form.i7_primer.errors.append("Please provide the i7 primer sequence.")

            if form.i5_kit.data == 0 and not form.i5_primer.data and form.index_type in [C.IndexType.DUAL_INDEX, C.IndexType.COMBINATORIAL_DUAL_INDEX]:
                form.i5_primer.errors.append("Please provide the i5 primer sequence.")
            if form.i5_kit.data == 0 and not form.i5_option.data and form.index_type in [C.IndexType.DUAL_INDEX, C.IndexType.COMBINATORIAL_DUAL_INDEX]:
                form.i5_option.errors.append("Please select how to proceed with the i5 index.")

            form.assert_valid()

            from ....core.context import ctx

            session = ctx.session
            barcode_table = form.barcode_table

            kit_i7_id = form.i7_kit.data
            kit_i7 = None
            kit_i7_df = None
            if kit_i7_id is not None and kit_i7_id > 0:
                selected_i7 = form.i7_kit.value or ""
                rc_i7 = selected_i7.endswith(" (Reverse Complement)")

                kit_i7 = session.get_one(Q.index_kit.select(id=kit_i7_id))
                kit_i7_df = session.pd.get_index_kit_barcodes(kit_i7.id, per_index=True)

                if rc_i7:
                    barcode_table["sequence_i7"] = barcode_table["sequence_i7"].apply(
                        lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None
                    )

                barcode_table["name_i7"] = barcode_table["sequence_i7"].map(
                    kit_i7_df.set_index("sequence_i7")["name_i7"]
                )
                barcode_table["kit_i7_id"] = kit_i7.id
                barcode_table["kit_i7"] = kit_i7.identifier
                barcode_table["orientation_i7_id"] = C.BarcodeOrientation.FORWARD.id
            elif form.i7_option.data == "rc":
                barcode_table["sequence_i7"] = barcode_table["sequence_i7"].apply(
                    lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None
                )
                barcode_table["orientation_i7_id"] = C.BarcodeOrientation.FORWARD_NOT_VALIDATED.id
            elif form.i7_option.data == "forward":
                barcode_table["orientation_i7_id"] = C.BarcodeOrientation.FORWARD_NOT_VALIDATED.id

            kit_i5_id = form.i5_kit.data
            if kit_i5_id is not None and kit_i5_id > 0:
                selected_i5 = form.i5_kit.value or ""
                rc_i5 = selected_i5.endswith(" (Reverse Complement)")

                if kit_i5_id == kit_i7_id:
                    assert kit_i7 is not None and kit_i7_df is not None
                    kit_i5 = kit_i7
                    kit_i5_df = kit_i7_df
                else:
                    kit_i5 = session.get_one(Q.index_kit.select(id=kit_i5_id))
                    kit_i5_df = session.pd.get_index_kit_barcodes(kit_i5.id, per_index=True)

                if rc_i5:
                    barcode_table["sequence_i5"] = barcode_table["sequence_i5"].apply(
                        lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None
                    )

                barcode_table["name_i5"] = barcode_table["sequence_i5"].map(kit_i5_df.set_index("sequence_i5")["name_i5"])
                barcode_table["kit_i5_id"] = kit_i5.id
                barcode_table["kit_i5"] = kit_i5.identifier
                barcode_table["orientation_i5_id"] = C.BarcodeOrientation.FORWARD.id
            elif form.i5_option.data == "rc":
                barcode_table["sequence_i5"] = barcode_table["sequence_i5"].apply(
                    lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None
                )
                barcode_table["orientation_i5_id"] = C.BarcodeOrientation.FORWARD_NOT_VALIDATED.id
            elif form.i5_option.data == "forward":
                barcode_table["orientation_i5_id"] = C.BarcodeOrientation.FORWARD_NOT_VALIDATED.id

            workflow.metadata["barcode_match_form"] = {
                "i7_kit": kit_i7_id,
                "i5_kit": kit_i5_id,
                "i7_option": form.i7_option.data,
                "i5_option": form.i5_option.data,
                "i7_primer": form.i7_primer.data,
                "i5_primer": form.i5_primer.data,
            }

            if form.i7_primer.data:
                workflow.add_comment(context="i7_primer", text=form.i7_primer.data)
            if form.i5_primer.data:
                workflow.add_comment(context="i5_primer", text=form.i5_primer.data)

            workflow.tables["barcode_table"] = barcode_table

            return workflow.get_next_step(form).make_response()
        return route
