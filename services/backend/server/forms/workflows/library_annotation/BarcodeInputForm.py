import pandas as pd
from fastapi import Depends, Response

from opengsync_db import categories as C

from ....core import dependencies
from ....components.tables import DropdownColumn, DuplicateCellValue
from ....utils import barcodes
from ...HTMXForm import RouteFunc, htmx_route
from ...common.BarcodeInputMixin import BarcodeInputMixin
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow, LibraryAnnotationWorkflowStep


def _eq_str(series: pd.Series, value: str) -> pd.Series:
    return series.astype("string").fillna("") == value


class BarcodeInputForm(BarcodeInputMixin, LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-barcode-input.html"

    spreadsheet = BarcodeInputMixin.make_spreadsheet(
        DropdownColumn("library_name", "Library Name", 250, choices=[], required=True),
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
        barcode_table = self.library_table[self.library_table["library_type_id"] != C.LibraryType.TENX_SC_ATAC.id].copy()
        self.spreadsheet.set_data(self.with_kit_ids(barcode_table))

    def check_clashes_within_pools(self, df: pd.DataFrame) -> None:
        """Libraries of one pool with the same index combination cannot be demultiplexed: a blocking error."""
        if "pool" not in self.library_table.columns:
            return
        pools = self.library_table.dropna(subset=["pool"]).drop_duplicates("library_name").set_index("library_name")["pool"]
        indexed = df[df["sequence_i7"].notna() & ~_eq_str(df["index_well"], "del")].copy()
        indexed["pool"] = indexed["library_name"].map(pools)
        indexed = indexed[indexed["pool"].notna()]
        if indexed["library_name"].nunique() < 2:
            return
        checked = barcodes.check_indices(indexed, groupby="pool")
        # the sheet groups by a typed label; name the pool as given in the pool step
        names: dict = {}
        if (pool_table := self.workflow.tables.get("pool_table")) is not None and {"pool_label", "pool_name"} <= set(pool_table.columns):
            names = dict(zip(pool_table["pool_label"], pool_table["pool_name"]))
        for idx in checked.index[checked["min_hamming_bases"] < 1]:
            pool = names.get(checked.at[idx, "pool"], checked.at[idx, "pool"])
            self.spreadsheet.add_error(idx, ["sequence_i7", "sequence_i5"], DuplicateCellValue(
                f"Same index combination as another library in pool '{pool}'; they could not be told apart."
            ))
        self.assert_valid()

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: BarcodeInputForm = Depends(BarcodeInputForm.Init()),
        ) -> Response:
            barcode_table = form.workflow.tables["barcode_table"]
            barcode_table = barcode_table[barcode_table["index_type_id"] != C.IndexType.TENX_ATAC_INDEX.id].copy()
            form.spreadsheet.set_data(form.with_kit_ids(barcode_table))
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: BarcodeInputForm = Depends(BarcodeInputForm.Validate()),
        ) -> Response:
            # Every (non-ATAC) library needs an index; ATAC indices are entered in the next step
            expected = form.library_table.loc[form.library_table["library_type_id"] != C.LibraryType.TENX_SC_ATAC.id, "library_name"]
            if len(missing := expected[~expected.isin(form.spreadsheet.data["library_name"])].tolist()) > 0:
                form.spreadsheet.add_general_error(f"Library names not found in the input: {', '.join(missing)}")
            df = form.validate_barcode_input()
            form.check_clashes_within_pools(df)
            form.workflow.tables["barcode_table"] = df
            return form.workflow.get_next_step(form).make_response()
        return route
