from typing import Self

import pandas as pd
from fastapi import Depends, Response

from opengsync_db import categories as C, models, SyncSession

from ....core import dependencies
from ....utils import parsing
from ....components import inputs
from ....components.tables import TextColumn, DuplicateCellValue, InvalidCellValue
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .MuxPrepWorkflow import MuxPrepWorkflow, MuxPrepWorkflowStep
from .FlexMuxForm import FlexMuxForm, _mux_barcode


def padded_ocm_barcode_id(s: int | str | None) -> str | None:
    if pd.isna(s):
        return None
    barcode_numbers = str(s).split(";")
    padded = [f"OB{''.join(filter(str.isdigit, bc))}" for bc in barcode_numbers]
    return ";".join(sorted(padded))


class OCMMuxForm(MuxPrepWorkflowStep):
    workflow: MuxPrepWorkflow
    template_path = "workflows/mux_prep/mux_prep-ocm_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            TextColumn(
                "demux_name", "Demultiplexed Name", 300, required=True, read_only=True,
                min_length=4, max_length=models.Sample.name.type.length,
            ),
            TextColumn(
                "sample_pool", "Sample Pool", 300, required=True, read_only=True,
                max_length=models.Sample.name.type.length,
                clean_up_fnc=parsing.make_alpha_numeric,
            ),
            TextColumn(
                "barcode_id", "Barcode ID", 200, required=True,
                max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH,
                clean_up_fnc=padded_ocm_barcode_id,
            ),
        ],
        allow_new_rows=False,
    )
    allowed_barcodes = [f"OB{i}" for i in range(1, 5)]

    def __init__(self, workflow: MuxPrepWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.sample_table = pd.DataFrame()

    @staticmethod
    def is_valid_barcode(s: str | None) -> bool:
        if pd.isna(s):
            return True
        return all(bc in OCMMuxForm.allowed_barcodes for bc in str(s).split(";"))

    @classmethod
    def build(cls, workflow: MuxPrepWorkflow, session: SyncSession) -> Self:
        sample_table = session.pd.get_lab_prep_pooling_table(workflow.lab_prep_id)
        sample_table = sample_table[sample_table["mux_type"].isin([C.MUXType.TENX_ON_CHIP])]
        mux_table = sample_table.drop_duplicates(subset=["sample_name", "sample_pool"], keep="first")

        template = pd.DataFrame({
            "demux_name": mux_table["sample_name"].values,
            "sample_pool": mux_table["sample_pool"].values,
            "barcode_id": mux_table["mux"].apply(_mux_barcode).values,
        })

        form = cls(workflow=workflow)
        form.sample_table = sample_table
        form.spreadsheet.configure(
            csrf_token=form.csrf_token_value,
            post_url=form.post_url,
            df=template,
        )
        form.spreadsheet.columns["sample_pool"].source = sample_table["sample_name"].unique().tolist()
        return form

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: MuxPrepWorkflow = Depends(MuxPrepWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> OCMMuxForm:
            return cls.build(workflow, session)
        return dependency

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: OCMMuxForm = Depends(OCMMuxForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: OCMMuxForm = Depends(OCMMuxForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            df = form.spreadsheet.data
            duplicate_barcode = df.duplicated(subset=["sample_pool", "barcode_id"], keep=False)
            known_samples = set(form.sample_table["sample_name"].values)

            for idx, row in df.iterrows():
                if row["demux_name"] not in known_samples:
                    form.spreadsheet.add_error(
                        idx, "demux_name",
                        InvalidCellValue(
                            f"Unknown sample '{row['demux_name']}'. Must be one of: {', '.join(form.sample_table['sample_name'].astype(str).unique())}"
                        ),
                    )
                if pd.notna(row["barcode_id"]) and not OCMMuxForm.is_valid_barcode(row["barcode_id"]):
                    form.spreadsheet.add_error(
                        idx, "barcode_id",
                        InvalidCellValue(f"'Barcode ID' must be one of: {', '.join(OCMMuxForm.allowed_barcodes)}"),
                    )
                elif duplicate_barcode.at[idx]:
                    form.spreadsheet.add_error(idx, "barcode_id", DuplicateCellValue("'Barcode ID' is duplicated in library."),)

            form.assert_valid()

            mapped = df.rename(columns={"demux_name": "sample_name"})
            sample_table = form.sample_table.copy()
            sample_table["mux_barcode"] = parsing.map_columns(
                sample_table, mapped, ["sample_name", "sample_pool"], "barcode_id"
            )
            FlexMuxForm.update_barcodes(session, sample_table)
            return form.workflow.complete_to_lab_prep()
        return route
