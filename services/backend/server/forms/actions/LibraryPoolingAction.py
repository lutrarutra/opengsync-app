import os

import pandas as pd
from fastapi import Depends, Response
from sqlalchemy import orm
from loguru import logger

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses
from ...components import inputs
from ...components.tables.spreadsheet import TextColumn, IntegerColumn, InvalidCellValue
from ...utils import parsing
from ..HTMXForm import RouteFunc, htmx_route, HTMXForm, FormFunc


class LibraryPoolingAction(HTMXForm):
    template_path = "workflows/library_pooling/library_pooling.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
        TextColumn("library_name", "Library Name", 300, required=True, read_only=True),
        TextColumn("pool", "Pool", 300, required=True),
    ])

    def __init__(self, lab_prep: models.LabPrep, library_table: pd.DataFrame):
        super().__init__()
        self.lab_prep = lab_prep
        self.library_table = library_table
        self.post_url = responses.url_for("LibraryPoolingAction.Begin", lab_prep_id=lab_prep.id)


    @classmethod
    def Init(cls) -> "FormFunc":
        def dependency(
            lab_prep_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            _ = Depends(dependencies.require_insider),
        ) -> "LibraryPoolingAction":
            lab_prep = session.get_one(Q.lab_prep.select(id=lab_prep_id))
            library_table = session.pd.get_lab_prep_libraries(lab_prep_id=lab_prep.id)

            flash = None
            if library_table["pool"].isna().any():
                if lab_prep.prep_file is not None:
                    if not os.path.exists(path := os.path.join("/media", lab_prep.prep_file.path)):
                        logger.warning(f"Lab prep file not found at {path}")
                        flash = responses.flash("Lab prep file not found..", "warning")
                    else:
                        prep_table = pd.read_excel(path, "prep_table")  # type: ignore
                        prep_table = prep_table.dropna(subset=["library_id", "library_name"])
                        if prep_table["library_id"].isna().any() or (~prep_table["library_id"].isin(library_table["library_id"])).any():
                            if not prep_table["library_name"].duplicated().any():
                                flash = responses.flash("Lab prep file is outdated, library_id mismatch. Attempting to map library_id using library_name. Please re-upload the lab prep file with correct library IDs to avoid potential issues.", "warning")
                                prep_table["library_id"] = prep_table["library_name"].map(
                                    dict(zip(library_table["library_name"], library_table["library_id"]))
                                )
                            else:
                                flash = responses.flash("Lab prep file is outdated, library_id mismatch. Please re-upload the lab prep file.", "warning")
                        order = prep_table["library_id"].tolist()
                        library_table["library_id"] = pd.Categorical(library_table["library_id"], categories=order, ordered=True)
                        library_table = library_table.sort_values("library_id").reset_index(drop=True)
                        library_table["library_id"] = library_table["library_id"].astype(pd.Int64Dtype())
                            
                        library_table["pool"] = parsing.map_columns(library_table, prep_table, idx_columns="library_id", col="pool")

            def clean_pool_value(value) -> str:
                if pd.isna(value):
                    return ""
                try:
                    value = int(value)
                    return str(value)
                except ValueError:
                    pass
                value = str(value).strip()
                if value.startswith(f"{lab_prep.name}_"):
                    value = value[len(f"{lab_prep.name}_") :]
                return value
            library_table["pool"] = library_table["pool"].apply(clean_pool_value).astype(str)
            form = cls(lab_prep=lab_prep, library_table=library_table)
            form._context["flash"] = flash
            return form
        return dependency
    
    @htmx_route("GET", "/{lab_prep_id}", name="Begin")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "LibraryPoolingAction" = Depends(LibraryPoolingAction.Init()),
        ) -> Response:
            return form.make_response(flash=form._context.pop("flash"))
        return route
    
    @htmx_route("POST", "/{lab_prep_id}", name="Submit")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "LibraryPoolingAction" = Depends(LibraryPoolingAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
        ) -> Response:
            df = form.spreadsheet.data
            if df.loc[~df["pool"].astype(str).str.strip().str.lower().isin(["x", "t", "skip"]), "pool"].isna().all():
                df.loc[df["pool"].isna(), "pool"] = "1"

            for idx, row in df.iterrows():
                if pd.notna(row["pool"]) and str(row["pool"]).strip().lower() == "x":
                    continue
                if pd.notna(row["pool"]) and str(row["pool"]).strip().lower() == "t":
                    if row["library_id"]:
                        form.spreadsheet.add_error(idx, "pool", InvalidCellValue("Requested library cannot be marked as control"))
                    else:
                        continue

                if row["library_id"] not in form.library_table["library_id"].values:
                    form.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                else:
                    try:
                        _id = int(row["library_id"])
                    except ValueError:
                        form.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                        _id = None

                    if _id is not None:
                        if (library := session.first(Q.library.select(id=_id))) is None:
                            form.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                        elif library.name != row["library_name"]:
                            form.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name' for 'library_id'"))
                        elif library.lab_prep_id != form.lab_prep.id:
                            form.spreadsheet.add_error(idx, "library_id", InvalidCellValue("Library is not part of this lab prep"))

                if form.library_table[form.library_table["library_id"] == row["library_id"]]["library_name"].isin([row["library_name"]]).all() == 0:
                    form.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name' for 'library_id'"))

            pooling_table = df.copy()
            pooling_table["old_pool_id"] = parsing.map_columns(pooling_table, form.library_table, "library_id", "pool_id")
            pooling_table["experiment_id"] = None

            for pool in form.lab_prep.pools:
                pooling_table.loc[pooling_table["old_pool_id"] == pool.id, "experiment_id"] = pool.experiment_id
                session.delete(pool)

            if len(pooling_table["pool"].unique()) == 1:
                pooling_table["pool"] = "1"
            
            # if all the experiment_ids are the same in the pool we can link it with the experiment
            experiment_mappings = {}
            for pool_suffix, _df in pooling_table.groupby("pool"):
                if len(_df["experiment_id"].unique()) == 1 and pd.notna(_df["experiment_id"].iloc[0]):
                    experiment_mappings[pool_suffix] = _df["experiment_id"].iloc[0]
                        
            if len(pooling_table["pool"].unique()) > 1:
                for pool_suffix, df in pooling_table.groupby("pool"):
                    if pool_suffix == "t" or pool_suffix == "skip":
                        continue
                    if pool_suffix == "x":
                        for _, row in df.iterrows():
                            library = session.get_one(Q.library.select(id=int(row["library_id"])))
                            library.status = C.LibraryStatus.FAILED
                            session.save(library)
                        continue

                    pool_suffix = str(pool_suffix).removeprefix(f"{form.lab_prep.name}_").strip()
                    pool = session.save(Q.pool.create(
                        name=f"{form.lab_prep.name}_{pool_suffix}", pool_type=C.PoolType.INTERNAL,
                        contact_email=current_user.email, contact_name=current_user.name, owner_id=current_user.id,
                        lab_prep_id=form.lab_prep.id, experiment_id=experiment_mappings.get(pool_suffix, None),
                        clone_number=0
                    ))
                    for _, row in df.iterrows():
                        library = session.get_one(Q.library.select(id=int(row["library_id"])))
                        library.pool_id = pool.id
                        library.status = C.LibraryStatus.POOLED
                        session.save(library)
                        
            elif len(pooling_table["pool"].unique()) > 0:
                pool = session.save(Q.pool.create(
                    name=form.lab_prep.name, pool_type=C.PoolType.INTERNAL,
                    contact_email=current_user.email, contact_name=current_user.name, owner_id=current_user.id,
                    lab_prep_id=form.lab_prep.id, experiment_id=experiment_mappings.get("1", None),
                    clone_number=0
                ))
                for _, row in pooling_table.iterrows():
                    library = session.get_one(Q.library.select(id=int(row["library_id"])))
                    library.pool_id = pool.id
                    library.status = C.LibraryStatus.POOLED
                    session.save(library)

            for seq_request_id in form.library_table["seq_request_id"].dropna().unique():
                seq_request = session.get_one(Q.seq_request.select(id=int(seq_request_id)).options(orm.selectinload(models.SeqRequest.libraries)))
                
                prepared = True
                for library in seq_request.libraries:
                    prepared = prepared and library.status.id >= C.LibraryStatus.POOLED.id

                if prepared and seq_request.status == C.SeqRequestStatus.ACCEPTED:
                    seq_request.status = C.SeqRequestStatus.PREPARED
                    session.save(seq_request)
            # TODO: render barcode clashes
            return responses.htmx_response(
                redirect=responses.url_for("lab_prep_page", lab_prep_id=form.lab_prep.id),
                flash=responses.flash("Library pooling completed!", "success")
            )
        return route




    