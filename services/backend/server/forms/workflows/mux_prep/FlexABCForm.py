from typing import Self

import pandas as pd
from fastapi import Depends, Response

from opengsync_db import categories as C, models, SyncSession

from ....core import dependencies
from ....utils import parsing
from ....components import inputs
from ....components.tables import IntegerColumn, TextColumn, DuplicateCellValue, InvalidCellValue
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .MuxPrepWorkflow import MuxPrepWorkflow, MuxPrepWorkflowStep
from .FlexMuxForm import FlexMuxForm, _mux_barcode


class FlexABCForm(MuxPrepWorkflowStep):
    workflow: MuxPrepWorkflow
    template_path = "workflows/mux_prep/mux_prep-flex_abc_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            IntegerColumn("sample_id", "Sample ID", 100, required=True, read_only=True),
            IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
            TextColumn("sample_pool", "Sample Pool", 300, required=True, read_only=True),
            TextColumn("sample_name", "Demultiplexed Name", 300, required=True, read_only=True),
            TextColumn("barcode_id", "Barcode ID", 200, required=False, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH),
        ],
        allow_new_rows=False,
    )
    allowed_barcodes = [f"AB{i:03}" for i in range(1, 17)]

    @classmethod
    def is_applicable(cls, workflow: MuxPrepWorkflow) -> bool:
        sample_table = workflow.tables.get("sample_table")
        if sample_table is None or sample_table.empty:
            return False
        return C.LibraryType.TENX_SC_ABC_FLEX in sample_table["library_type"].values

    @staticmethod
    def _abc_table(workflow: MuxPrepWorkflow) -> pd.DataFrame:
        sample_table = workflow.tables["sample_table"]
        gex_table = workflow.tables["gex_table"]
        abc_table = sample_table[
            (sample_table["mux_type"].isin([C.MUXType.TENX_FLEX_PROBE]))
            & (sample_table["library_type"].isin([C.LibraryType.TENX_SC_ABC_FLEX]))
        ].copy()
        abc_table["gex_barcode"] = parsing.map_columns(abc_table, gex_table, "sample_name", "mux_barcode")
        abc_table["barcode_id"] = abc_table["mux"].apply(_mux_barcode)
        missing = abc_table["barcode_id"].isna()
        abc_table.loc[missing, "barcode_id"] = abc_table.loc[missing, "gex_barcode"].apply(
            lambda x: x.replace("BC", "AB") if pd.notna(x) else None
        )
        return abc_table.drop(columns=["gex_barcode"])

    @classmethod
    def build(cls, workflow: MuxPrepWorkflow) -> Self:
        form = cls(workflow=workflow)
        form.spreadsheet.configure(
            csrf_token=form.csrf_token_value,
            post_url=form.post_url,
            df=cls._abc_table(workflow),
        )
        return form

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: MuxPrepWorkflow = Depends(MuxPrepWorkflow.Init(cls.__name__)),
        ) -> FlexABCForm:
            return cls.build(workflow)
        return dependency

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: FlexABCForm = Depends(FlexABCForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: FlexABCForm = Depends(FlexABCForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            df = form.spreadsheet.data
            gex_table = form.workflow.tables["gex_table"]
            sample_table = form.workflow.tables["sample_table"]

            df["sample_pool"] = parsing.map_columns(df, gex_table, "sample_name", "sample_pool")
            duplicate_barcode = df.duplicated(subset=["sample_pool", "barcode_id"], keep=False)

            for idx, row in df.iterrows():
                if row["sample_name"] not in sample_table["sample_name"].values:
                    form.spreadsheet.add_error(
                        idx, "sample_name",
                        InvalidCellValue(
                            f"Unknown sample '{row['sample_name']}'. Must be one of: {', '.join(sample_table['sample_name'].astype(str).unique())}"
                        ),
                    )
                if pd.notna(row["barcode_id"]) and row["barcode_id"] not in FlexABCForm.allowed_barcodes:
                    form.spreadsheet.add_error(
                        idx, "barcode_id",
                        InvalidCellValue(f"'Barcode ID' must be one of: {', '.join(FlexABCForm.allowed_barcodes)}"),
                    )
                if pd.notna(row["barcode_id"]) and duplicate_barcode.at[idx]:
                    form.spreadsheet.add_error(
                        idx, "barcode_id",
                        DuplicateCellValue("'Barcode ID' is duplicated in library."),
                    )

            form.assert_valid()

            abc_table = sample_table[
                (sample_table["mux_type"].isin([C.MUXType.TENX_FLEX_PROBE]))
                & (sample_table["library_type"].isin([C.LibraryType.TENX_SC_ABC_FLEX]))
            ].copy()
            abc_table["mux_barcode"] = parsing.map_columns(
                abc_table, df, ["sample_name", "library_id"], "barcode_id"
            )
            combined = pd.concat([abc_table, gex_table], ignore_index=True).reset_index(drop=True)
            FlexMuxForm.update_barcodes(session, combined)
            return form.workflow.complete_to_lab_prep()
        return route
