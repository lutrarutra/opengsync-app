from typing import Self

import pandas as pd
from fastapi import Depends, Response
from loguru import logger
from pydantic import BaseModel

from opengsync_db import categories as C, models, SyncSession, queries as Q

from ....core import dependencies, exceptions as exc
from ....utils import parsing
from ....components import inputs
from ....components.tables import IntegerColumn, TextColumn, DuplicateCellValue
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .MuxPrepWorkflow import MuxPrepWorkflow, MuxPrepWorkflowStep


def _mux_barcode(value) -> str | None:
    if pd.notna(value) and isinstance(value, dict):
        return value.get("barcode")
    return None


class FlexBarcodeKey(BaseModel):
    sample_id: int
    library_id: int
    mux_barcode: str


class FlexMuxForm(MuxPrepWorkflowStep):
    workflow: MuxPrepWorkflow
    template_path = "workflows/mux_prep/mux_prep-flex_annotation.html"
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

    def __init__(self, workflow: MuxPrepWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.sample_table = pd.DataFrame()
        self.flex_table = pd.DataFrame()

    @staticmethod
    def update_barcodes(session: SyncSession, sample_table: pd.DataFrame) -> None:
        for key, _df in parsing.safe_groupby(
            sample_table,
            ["sample_id", "library_id", "mux_barcode"],
            FlexBarcodeKey,
            dropna=True,
        ):
            link = session.first(
                Q.links.get_sample_library_link(sample_id=key.sample_id, library_id=key.library_id)
            )
            if link is None:
                logger.error(
                    f"SampleLibraryLink not found for sample_id={key.sample_id}, library_id={key.library_id}."
                )
                raise exc.NotFoundException(
                    f"SampleLibraryLink not found for sample_id={key.sample_id}, library_id={key.library_id}."
                )
            mux = dict(link.mux) if link.mux else {}
            mux["barcode"] = key.mux_barcode
            link.mux = mux
            session.save(link)

    @classmethod
    def build(cls, workflow: MuxPrepWorkflow, session: SyncSession) -> Self:
        sample_table = session.pd.get_lab_prep_pooling_table(workflow.lab_prep_id)
        sample_table = sample_table[sample_table["mux_type"].isin([C.MUXType.TENX_FLEX_PROBE])]
        flex_table = sample_table[
            (sample_table["mux_type"].isin([C.MUXType.TENX_FLEX_PROBE]))
            & (sample_table["library_type"].isin([C.LibraryType.TENX_SC_GEX_FLEX]))
        ].copy()
        flex_table["barcode_id"] = flex_table["mux"].apply(_mux_barcode)

        form = cls(workflow=workflow)
        form.sample_table = sample_table
        form.flex_table = flex_table
        form.spreadsheet.configure(
            csrf_token=form.csrf_token_value,
            post_url=form.post_url,
            df=flex_table,
        )
        return form

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: MuxPrepWorkflow = Depends(MuxPrepWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> FlexMuxForm:
            return cls.build(workflow, session)
        return dependency

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: FlexMuxForm = Depends(FlexMuxForm.Init()),
        ) -> Response:
            gex_table = form.workflow.tables.get("gex_table")
            if gex_table is not None:
                df = gex_table.copy()
                if "mux_barcode" in df.columns:
                    df["barcode_id"] = df["mux_barcode"]
                form.spreadsheet.set_data(df)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: FlexMuxForm = Depends(FlexMuxForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            from .FlexABCForm import FlexABCForm

            df = form.spreadsheet.data
            duplicate_barcode = df.duplicated(subset=["sample_pool", "barcode_id"], keep=False)

            for idx, row in df.iterrows():
                if pd.notna(row["barcode_id"]) and duplicate_barcode.at[idx]:
                    form.spreadsheet.add_error(idx, "barcode_id", DuplicateCellValue("'Barcode ID' is duplicated in library."),)

            form.assert_valid()

            form.flex_table["mux_barcode"] = parsing.map_columns(form.flex_table, df, ["sample_id", "library_id"], "barcode_id")
            form.workflow.tables["sample_table"] = form.sample_table
            form.workflow.tables["gex_table"] = form.flex_table

            if FlexABCForm.is_applicable(form.workflow):
                return form.workflow.get_next_step(form).make_response()

            FlexMuxForm.update_barcodes(session, form.flex_table)
            return form.workflow.complete_to_lab_prep()
        return route
