from typing import Self

import pandas as pd
from fastapi import Depends, Response
from pydantic import BaseModel

from opengsync_db import models, SyncSession, queries as Q

from ....core import dependencies, exceptions as exc
from ....utils import parsing
from ....components import inputs
from ....components.tables import CategoricalDropDown
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .SelectLibraryProtocolsWorkflow import SelectLibraryProtocolsWorkflow, SelectLibraryProtocolsWorkflowStep


class LibraryProtocolRow(BaseModel):
    library_id: int
    protocol_id: int | None = None


class LibraryProtocolSelectForm(SelectLibraryProtocolsWorkflowStep):
    workflow: SelectLibraryProtocolsWorkflow
    template_path = "workflows/select_library_protocols/select_library_protocol.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            CategoricalDropDown("library_id", "Library", 300, categories={}, required=True),
            CategoricalDropDown("protocol_id", "Protocol", 1000, categories={}, required=False),
        ],
        allow_new_rows=False,
    )

    def __init__(self, workflow: SelectLibraryProtocolsWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.lab_prep: models.LabPrep | None = None
        self.library_table = pd.DataFrame()

    @classmethod
    def build(
        cls,
        workflow: SelectLibraryProtocolsWorkflow,
        session: SyncSession,
        library_table: pd.DataFrame | None = None,
    ) -> Self:
        lab_prep = session.get_one(Q.lab_prep.select(id=workflow.lab_prep_id))
        library_mappings = {lib.id: lib.name for lib in lab_prep.libraries}
        protocol_mappings = {
            protocol.id: protocol.name
            for protocol in session.get_all(Q.protocol.select(), order_by=models.Protocol.name.desc(), limit=None)
        }

        if library_table is None:
            library_table = workflow.tables.get("library_table")
        if library_table is None:
            library_table = pd.DataFrame({
                "library_id": [library.id for library in lab_prep.libraries],
                "protocol_id": [library.protocol_id for library in lab_prep.libraries],
            })

        library_table = library_table.copy()
        library_table["library_id"] = library_table["library_id"].astype(pd.Int64Dtype())
        if "protocol_id" not in library_table.columns:
            library_table["protocol_id"] = None
        library_table["protocol_id"] = library_table["protocol_id"].astype(pd.Int64Dtype())
        workflow.tables["library_table"] = library_table

        form = cls(workflow=workflow)
        form.lab_prep = lab_prep
        form.library_table = library_table
        form._context["lab_prep"] = lab_prep
        form.spreadsheet.columns["library_id"].set_categories(library_mappings)
        form.spreadsheet.columns["protocol_id"].set_categories(protocol_mappings)
        form.spreadsheet.configure(
            csrf_token=form.csrf_token_value,
            post_url=form.post_url,
            df=library_table,
        )
        return form

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: SelectLibraryProtocolsWorkflow = Depends(SelectLibraryProtocolsWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> LibraryProtocolSelectForm:
            return cls.build(workflow, session)
        return dependency

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: LibraryProtocolSelectForm = Depends(LibraryProtocolSelectForm.Init()),
        ) -> Response:
            library_table = form.workflow.tables.get("library_table")
            if library_table is not None:
                form.spreadsheet.set_data(library_table)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: LibraryProtocolSelectForm = Depends(LibraryProtocolSelectForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            df = form.spreadsheet.data
            form.assert_valid()

            for _, row in parsing.safe_iter(df, LibraryProtocolRow):
                library = session.first(Q.library.select(id=row.library_id))
                if library is None:
                    raise exc.NotFoundException(f"Library {row.library_id} not found.")
                if library.lab_prep_id != form.workflow.lab_prep_id:
                    raise exc.BadRequestException("Library is not part of this lab prep.")
                library.protocol_id = row.protocol_id
                session.save(library)

            return form.workflow.complete_to_lab_prep()
        return route
