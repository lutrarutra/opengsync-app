import pandas as pd
from fastapi import Depends, Response

from opengsync_db import models, queries as Q, categories as C, SyncSession

from opengsync_db.core.blueprints import pd_transforms as T

from ....core import context, dependencies
from ....utils import barcodes
from ....components import inputs
from ....components.tables.spreadsheet import DBObjectColumn, TextColumn, CategoricalDropDown, InvalidCellValue, MissingCellValue
from ...HTMXForm import RouteFunc, htmx_route
from .ReindexWorkflow import ReindexWorkflowStep, ReindexWorkflow
from .BarcodeInputForm import assert_libraries_listed


class TENXATACBarcodeInputForm(ReindexWorkflowStep):
    template_path = "workflows/reindex/barcode-input.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            DBObjectColumn(
                columns=("library_id", "library_name"),
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
            TextColumn("name", "Name", 150, required=False, max_length=models.LibraryIndex.name_i7.type.length),
            # Optional: a kit + well/name fills them (as legacy CommonTENXATACBarcodeInputForm)
            *[
                TextColumn(
                    f"sequence_{i}", f"Sequence {i}", 180, max_length=models.LibraryIndex.sequence_i7.type.length,
                    clean_up_fnc=barcodes.clean_sequence, validation_fnc=barcodes.check_sequence,
                )
                for i in range(1, 5)
            ],
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

    def resolve_kits(self, session: SyncSession, df: pd.DataFrame) -> pd.DataFrame:
        """Fill name and sequences from the kit (by well or name) and set ``kit_id``; add errors for
        rows without a kit barcode or four sequences. Same rules as library annotation's ATAC step."""
        df.loc[df["index_well"].notna(), "index_well"] = (
            df.loc[df["index_well"].notna(), "index_well"].astype(str).str.strip().str.replace(r"(?<=[A-Z])0+(?=\d)", "", regex=True)
        )
        sequence_columns = [f"sequence_{i}" for i in range(1, 5)]
        kit_defined = df["kit"].notna() & (df["index_well"].notna() | df["name"].notna())
        manual_defined = df[sequence_columns].notna().all(axis=1)

        df["kit_id"] = None
        for identifier in df["kit"].dropna().unique().tolist():
            kit = session.get_one(Q.index_kit.select(identifier=identifier))
            kit_df = T.index_kit_barcodes_per_index(
                T.index_kit_barcodes(session.get_pandas(Q.pd.index_kit_barcodes(kit.id), limit=None), per_adapter=False, per_index=True),
                kit.type,
            )
            # One row per well: name + sequence_1..4 (per_index yields four i7 rows per well)
            kit_df = kit_df.groupby(["well", "name_i7"], sort=False)["sequence_i7"].agg(list).reset_index().rename(columns={"name_i7": "name"})
            df.loc[df["kit"] == identifier, "kit_id"] = kit.id
            view = df["kit"] == identifier
            for _, kit_row in kit_df.iterrows():
                df.loc[view & (df["index_well"] == kit_row["well"]), "name"] = kit_row["name"]
                for i, sequence in enumerate(kit_row["sequence_i7"][:4], start=1):
                    df.loc[view & (df["name"] == kit_row["name"]), f"sequence_{i}"] = sequence

        for idx, row in df.iterrows():
            if pd.notna(row["index_well"]) and row["index_well"] == "del":
                continue
            if kit_defined.at[idx]:
                if row[sequence_columns].isna().any():
                    column = "name" if pd.notna(row["name"]) else "index_well"
                    self.spreadsheet.add_error(idx, column, InvalidCellValue(f"'{row[column]}' not found in kit '{row['kit']}'"))
            elif not manual_defined.at[idx]:
                if pd.notna(row["kit"]):
                    self.spreadsheet.add_error(idx, ["index_well", "name"], MissingCellValue("'Index Well' or 'Name' must be defined when kit is defined"))
                else:
                    self.spreadsheet.add_error(
                        idx, ["kit", "name", *sequence_columns],
                        MissingCellValue("missing 'Sequence 1/2/3/4' or 'Name' + 'Kit' or 'Index Well' + 'Kit'"),
                    )
        return df

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
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            df = form.resolve_kits(session, form.spreadsheet.data.copy())
            assert_libraries_listed(form, df, atac=True)
            form.assert_valid()
            form.spreadsheet.set_data(df)
            form.workflow.tables["tenx_atac_barcode_table"] = df
            next_step = form.workflow.get_next_step(form)
            return next_step.make_response()
        return route