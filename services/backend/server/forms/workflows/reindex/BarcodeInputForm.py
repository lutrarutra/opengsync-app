from fastapi import Depends, Response
import pandas as pd

from opengsync_db import categories as C

from ....components.tables import DBObjectColumn
from ...HTMXForm import RouteFunc, htmx_route
from ...common.BarcodeInputMixin import BarcodeInputMixin
from .ReindexWorkflow import ReindexWorkflowStep, ReindexWorkflow


def assert_libraries_listed(
    form: ReindexWorkflowStep,
    df: pd.DataFrame,
    *,
    atac: bool,
) -> None:
    """Require every selected library of this type to appear at least once."""
    library_table = form.workflow.tables["library_table"]
    if atac:
        expected = library_table.loc[
            library_table["library_type"] == C.LibraryType.TENX_SC_ATAC,
            ["library_id", "library_name"],
        ].copy()
    else:
        expected = library_table.loc[
            library_table["library_type"] != C.LibraryType.TENX_SC_ATAC,
            ["library_id", "library_name"],
        ].copy()

    listed: list[int] = []
    if not df.empty and "library_id" in df.columns:
        for value in df["library_id"].tolist():
            if value is None:
                continue
            try:
                listed.append(int(value))
            except (TypeError, ValueError):
                continue

    missing = expected.loc[~expected["library_id"].isin(listed)].copy()
    if missing.empty:
        return

    names = ", ".join(
        f"{row['library_name']} [{int(row['library_id'])}]"
        for _, row in missing.iterrows()
    )
    form.spreadsheet.add_general_error(  # type: ignore[attr-defined]
        f"Each selected library must be listed at least once. Missing: {names}"
    )


class BarcodeInputForm(BarcodeInputMixin, ReindexWorkflowStep):
    template_path = "workflows/reindex/barcode-input.html"

    spreadsheet = BarcodeInputMixin.make_spreadsheet(
        DBObjectColumn(
            columns=("library_id", "library_name"),
            types=(int, str),
            label="Library",
            width=300,
            categories={},
            required=True,
        ),
    )

    @classmethod
    def is_applicable(cls, workflow: "ReindexWorkflow") -> bool:
        library_table = workflow.tables["library_table"]
        return bool((library_table["library_type"] != C.LibraryType.TENX_SC_ATAC).any())

    def __init__(self, workflow: "ReindexWorkflow") -> None:
        super().__init__(workflow=workflow)
        self.library_table = self.workflow.tables["library_table"]
        self.barcode_table = self.workflow.tables["barcode_table"]

        self.spreadsheet.columns["Library"].set_categories({
            row["library_id"]: f"{row['library_name']} [{row['library_id']}]"
            for _, row in self.library_table.iterrows()
            if row["library_type"] != C.LibraryType.TENX_SC_ATAC
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
            assert_libraries_listed(form, df, atac=False)
            form.assert_valid()
            form.workflow.tables["barcode_table"] = df
            return form.workflow.get_next_step(form).make_response()
        return route