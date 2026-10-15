from typing import Self
import os

import pandas as pd
from fastapi import Depends, Response
from loguru import logger

from opengsync_db import models, SyncSession, queries as Q

from opengsync_db.core.blueprints import pd_transforms as T

from ....core import dependencies, responses, config
from ....components import inputs
from ....components.tables.spreadsheet import TextColumn, FloatColumn, DBObjectColumn, InvalidCellValue, MissingCellValue
from ....utils import parsing
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LibraryPoolingWorkflow import LibraryPoolingWorkflow, LibraryPoolingWorkflowStep


class LibraryPoolingForm(LibraryPoolingWorkflowStep):
    workflow: LibraryPoolingWorkflow
    template_path = "workflows/library_pooling/library_pooling.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            # Categories are the lab prep's libraries, set in build
            DBObjectColumn(("library_id", "library_name"), "Library", 300, categories={}, required=True, read_only=True),
            TextColumn("pool", "Pool", 300, required=True),
            FloatColumn("num_m_reads_requested", "M Reads Requested", 150),
        ],
        allow_new_rows=False,
    )

    def __init__(self, workflow: LibraryPoolingWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.lab_prep: models.LabPrep | None = None
        self.library_table = pd.DataFrame()
        # Warning about the prep file, shown on Begin (not part of the template context, which
        # make_response() also receives on re-render)
        self.prefill_flash = None

    @classmethod
    def build(cls, workflow: LibraryPoolingWorkflow, session: SyncSession) -> Self:
        lab_prep = session.get_one(Q.lab_prep.select(id=workflow.lab_prep_id))
        library_table = T.lab_prep_libraries(
            session.get_pandas(Q.pd.lab_prep_libraries(lab_prep.id), limit=None)
        )
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
                    # one prep table row per index: a library may span several rows
                    if not prep_table.drop_duplicates(subset=["library_id", "library_name"])["library_name"].duplicated().any():
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
                # prep table can have multiple rows per library (one per index): order by first occurrence,
                # take the first pool given; libraries missing from the prep table go last
                prep_table = prep_table.dropna(subset=["library_id"])
                order = {library_id: i for i, library_id in enumerate(prep_table["library_id"].drop_duplicates())}
                library_table = library_table.sort_values(
                    "library_id", key=lambda s: s.map(order), na_position="last", kind="stable"
                ).reset_index(drop=True)
                pools = prep_table.dropna(subset=["pool"]).drop_duplicates(subset="library_id", keep="first")
                library_table["pool"] = parsing.map_columns(library_table, pools, idx_columns="library_id", col="pool")

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
        form.prefill_flash = flash
        form.spreadsheet.columns["Library"].set_categories({
            int(library.library_id): f"{library.library_name} [{library.library_id}]"
            for library in library_table.itertuples()
        })
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
        ) -> Response:
            df = form.spreadsheet.data
            if df.loc[~df["pool"].astype(str).str.strip().str.lower().isin(["x", "t", "skip"]), "pool"].isna().all():
                df.loc[df["pool"].isna(), "pool"] = "1"

            # one value per pool: required and >= 0 for pooled rows, identical within a pool
            pool_num_m_reads: dict[str, float] = {}
            for idx, row in df.iterrows():
                pool = str(row["pool"]).strip() if pd.notna(row["pool"]) else ""
                if pool.lower() in ("", "x", "t", "skip"):
                    continue
                num_m_reads = row["num_m_reads_requested"]
                if pd.isna(num_m_reads):
                    form.spreadsheet.add_error(idx, "num_m_reads_requested", MissingCellValue("Number of M reads requested is required"))
                elif float(num_m_reads) < 0:
                    form.spreadsheet.add_error(idx, "num_m_reads_requested", InvalidCellValue("Number of M reads requested must be >= 0"))
                elif pool_num_m_reads.setdefault(pool, float(num_m_reads)) != float(num_m_reads):
                    form.spreadsheet.add_error(idx, "num_m_reads_requested", InvalidCellValue(f"All libraries in pool '{pool}' must have the same number of M reads requested"))

            # the Library column only accepts the prep's libraries (id and name), so every row is one of them
            for idx, row in df.iterrows():
                pool = str(row["pool"]).strip().lower() if pd.notna(row["pool"]) else ""
                if pool == "t":
                    form.spreadsheet.add_error(idx, "pool", InvalidCellValue("Requested library cannot be marked as control"))

            form.assert_valid()

            form.workflow.tables["pooling_table"] = df
            form.workflow.tables["library_table"] = form.library_table
            return form.workflow.get_next_step(form).make_response()
        return route
