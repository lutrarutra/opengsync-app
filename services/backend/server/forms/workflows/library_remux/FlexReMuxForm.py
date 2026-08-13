from typing import Self

import pandas as pd
from fastapi import Depends, Response
from sqlalchemy import orm

from opengsync_db import categories as C, models, SyncSession, queries as Q

from ....core import dependencies, exceptions as exc
from ....utils import parsing
from ....components import inputs
from ....components.tables import IntegerColumn, TextColumn, DuplicateCellValue
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LibraryRemuxWorkflow import LibraryRemuxWorkflow, LibraryRemuxWorkflowStep
from ..mux_prep.FlexMuxForm import FlexMuxForm


class FlexReMuxForm(LibraryRemuxWorkflowStep):
    workflow: LibraryRemuxWorkflow
    template_path = "workflows/library_remux/flex_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            IntegerColumn("sample_id", "Sample ID", 100, required=True, read_only=True),
            IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
            TextColumn("sample_name", "Demultiplexed Name", 300, required=True, read_only=True),
            TextColumn(
                "barcode_id", "Barcode ID", 200, required=False,
                max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH,
            ),
        ],
        allow_new_rows=False,
    )

    def __init__(self, workflow: LibraryRemuxWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.flex_table = pd.DataFrame()

    @classmethod
    def build(cls, workflow: LibraryRemuxWorkflow, session: SyncSession) -> Self:
        library = session.get_one(
            Q.library.select(id=workflow.library_id),
            options=[orm.selectinload(models.Library.sample_links)],
        )
        if library.type not in [C.LibraryType.TENX_SC_GEX_FLEX, C.LibraryType.TENX_SC_ABC_FLEX]:
            raise exc.BadRequestException(
                f"Library type {library.type} is not supported for FlexReMuxForm"
            )

        rows = [
            {
                "sample_id": link.sample_id,
                "library_id": library.id,
                "sample_name": link.sample.name,
                "barcode_id": link.mux.get("barcode") if link.mux is not None else None,
            }
            for link in library.sample_links
        ]
        flex_table = pd.DataFrame(rows, columns=["sample_id", "library_id", "sample_name", "barcode_id"])

        form = cls(workflow=workflow)
        form.flex_table = flex_table
        form._context["library"] = library
        form.spreadsheet.configure(
            csrf_token=form.csrf_token_value,
            post_url=form.post_url,
            df=flex_table,
        )
        return form

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: LibraryRemuxWorkflow = Depends(LibraryRemuxWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> FlexReMuxForm:
            return cls.build(workflow, session)
        return dependency

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: FlexReMuxForm = Depends(FlexReMuxForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            df = form.spreadsheet.data
            duplicate_barcode = df.duplicated(subset=["barcode_id"], keep=False) & pd.notna(df["barcode_id"])

            for idx, row in df.iterrows():
                if duplicate_barcode.at[idx]:
                    form.spreadsheet.add_error(
                        idx, "barcode_id",
                        DuplicateCellValue("Duplicate 'Barcode ID' in the same 'Sample Pool' is not allowed."),
                    )

            form.assert_valid()

            form.flex_table["mux_barcode"] = parsing.map_columns(
                form.flex_table, df, ["sample_id", "library_id"], "barcode_id",
            )
            FlexMuxForm.update_barcodes(session, form.flex_table)
            return form.workflow.complete_to_library()
        return route
