from typing import Self
import os

import pandas as pd
from fastapi import Depends, Response
from loguru import logger

from opengsync_db import models, SyncSession, queries as Q

from ....core import dependencies, responses, config
from ....components import inputs
from ....components.tables.spreadsheet import TextColumn, IntegerColumn, InvalidCellValue
from ....utils import parsing
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LibraryPoolingWorkflow import LibraryPoolingWorkflow, LibraryPoolingWorkflowStep


class LibraryPoolingForm(LibraryPoolingWorkflowStep):
    workflow: LibraryPoolingWorkflow
    template_path = "workflows/library_pooling/library_pooling.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
            TextColumn("library_name", "Library Name", 300, required=True, read_only=True),
            TextColumn("pool", "Pool", 300, required=True),
        ],
        allow_new_rows=False,
    )

    def __init__(self, workflow: LibraryPoolingWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.lab_prep: models.LabPrep | None = None
        self.library_table = pd.DataFrame()

    @classmethod
    def build(cls, workflow: LibraryPoolingWorkflow, session: SyncSession) -> Self:
        lab_prep = session.get_one(Q.lab_prep.select(id=workflow.lab_prep_id))
        library_table = session.pd.get_lab_prep_libraries(lab_prep_id=lab_prep.id)
        flash = None

        if library_table["pool"].isna().any() and lab_prep.prep_file is not None:
            path = os.path.join(config.settings.app_config.media_folder, lab_prep.prep_file.path)
            if not os.path.exists(path):
                logger.warning(f"Lab prep file not found at {path}")
                flash = responses.flash("Lab prep file not found..", "warning")
            else:
                prep_table = pd.read_excel(path, "prep_table")
                prep_table = prep_table.dropna(subset=["library_id", "library_name"])
                if prep_table["library_id"].isna().any() or (~prep_table["library_id"].isin(library_table["library_id"])).any():
                    if not prep_table["library_name"].duplicated().any():
                        flash = responses.flash(
                            "Lab prep file is outdated, library_id mismatch. Attempting to map library_id using library_name. Please re-upload the lab prep file with correct library IDs to avoid potential issues.",
                            "warning",
                        )
                        prep_table["library_id"] = prep_table["library_name"].map(
                            dict(zip(library_table["library_name"], library_table["library_id"]))
                        )
                    else:
                        flash = responses.flash(
                            "Lab prep file is outdated, library_id mismatch. Please re-upload the lab prep file.",
                            "warning",
                        )
                order = prep_table["library_id"].tolist()
                library_table["library_id"] = pd.Categorical(library_table["library_id"], categories=order, ordered=True)
                library_table = library_table.sort_values("library_id").reset_index(drop=True)
                library_table["library_id"] = library_table["library_id"].astype(pd.Int64Dtype())
                library_table["pool"] = parsing.map_columns(library_table, prep_table, idx_columns="library_id", col="pool")

        def clean_pool_value(value) -> str:
            if pd.isna(value):
                return ""
            try:
                return str(int(value))
            except (TypeError, ValueError):
                pass
            value = str(value).strip()
            prefix = f"{lab_prep.name}_"
            if value.startswith(prefix):
                value = value[len(prefix):]
            return value

        library_table["pool"] = library_table["pool"].apply(clean_pool_value).astype(str)

        form = cls(workflow=workflow)
        form.lab_prep = lab_prep
        form.library_table = library_table
        form._context["flash"] = flash
        form.spreadsheet.configure(
            csrf_token=form.csrf_token_value,
            post_url=form.post_url,
            df=library_table,
        )
        return form

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: LibraryPoolingWorkflow = Depends(LibraryPoolingWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> LibraryPoolingForm:
            return cls.build(workflow, session)
        return dependency

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: LibraryPoolingForm = Depends(LibraryPoolingForm.Init()),
        ) -> Response:
            pooling_table = form.workflow.tables.get("pooling_table")
            if pooling_table is not None:
                form.spreadsheet.set_data(pooling_table)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: LibraryPoolingForm = Depends(LibraryPoolingForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            df = form.spreadsheet.data
            if df.loc[~df["pool"].astype(str).str.strip().str.lower().isin(["x", "t", "skip"]), "pool"].isna().all():
                df.loc[df["pool"].isna(), "pool"] = "1"

            assert form.lab_prep is not None
            for idx, row in df.iterrows():
                pool = str(row["pool"]).strip().lower() if pd.notna(row["pool"]) else ""
                if pool == "x":
                    continue
                if pool == "t":
                    if row["library_id"]:
                        form.spreadsheet.add_error(idx, "pool", InvalidCellValue("Requested library cannot be marked as control"))
                    continue

                if row["library_id"] not in form.library_table["library_id"].values:
                    form.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                    continue

                try:
                    library_id = int(row["library_id"])
                except (TypeError, ValueError):
                    form.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                    continue

                library = session.first(Q.library.select(id=library_id))
                if library is None:
                    form.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                elif library.name != row["library_name"]:
                    form.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name' for 'library_id'"))
                elif library.lab_prep_id != form.lab_prep.id:
                    form.spreadsheet.add_error(idx, "library_id", InvalidCellValue("Library is not part of this lab prep"))

                if form.library_table[form.library_table["library_id"] == row["library_id"]]["library_name"].isin([row["library_name"]]).all() == 0:
                    form.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name' for 'library_id'"))

            form.assert_valid()

            form.workflow.tables["pooling_table"] = df
            form.workflow.tables["library_table"] = form.library_table
            return form.workflow.get_next_step(form).make_response()
        return route
