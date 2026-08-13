from fastapi import Depends, Response
from sqlalchemy import orm
import pandas as pd
from pydantic import BaseModel

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, responses
from ....core.context import ctx
from ....utils import parsing, barcodes
from ...HTMXForm import RouteFunc, htmx_route
from .LibraryPoolingWorkflow import LibraryPoolingWorkflow, LibraryPoolingWorkflowStep


class PoolGroupKey(BaseModel):
    pool: str


class PooledLibraryRow(BaseModel):
    library_id: int


class CompleteLibraryPoolingForm(LibraryPoolingWorkflowStep):
    workflow: LibraryPoolingWorkflow
    template_path = "workflows/library_pooling/complete-pooling.html"

    def __init__(self, workflow: LibraryPoolingWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.barcode_table = None
        self.lab_prep: models.LabPrep | None = None

    def prepare(self) -> None:
        session = ctx.session
        self.lab_prep = session.get_one(Q.lab_prep.select(id=self.workflow.lab_prep_id))
        pooling_table = self.workflow.tables["pooling_table"]
        barcode_table = session.pd.get_lab_prep_barcodes(self.workflow.lab_prep_id)
        barcode_table["pool"] = parsing.map_columns(barcode_table, pooling_table, "library_id", "pool")
        self.barcode_table = barcodes.check_indices(barcode_table, groupby="pool")
        self._context["lab_prep"] = self.lab_prep

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: CompleteLibraryPoolingForm = Depends(CompleteLibraryPoolingForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: CompleteLibraryPoolingForm = Depends(CompleteLibraryPoolingForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            lab_prep = session.get_one(
                Q.lab_prep.select(id=form.workflow.lab_prep_id).options(
                    orm.selectinload(models.LabPrep.pools),
                )
            )
            pooling_table = form.workflow.tables["pooling_table"].copy()
            library_table = form.workflow.tables["library_table"]

            pooling_table["old_pool_id"] = parsing.map_columns(pooling_table, library_table, "library_id", "pool_id")
            pooling_table["experiment_id"] = None

            for pool in lab_prep.pools:
                pooling_table.loc[pooling_table["old_pool_id"] == pool.id, "experiment_id"] = pool.experiment_id
                session.delete(pool)

            if len(pooling_table["pool"].unique()) == 1:
                pooling_table["pool"] = "1"

            experiment_mappings: dict[str, int] = {}
            for key, group in parsing.safe_groupby(pooling_table, "pool", PoolGroupKey):
                experiment_ids = group["experiment_id"].unique()
                if len(experiment_ids) == 1 and pd.notna(experiment_ids[0]):
                    experiment_mappings[key.pool] = int(experiment_ids[0])

            def _experiment_id(pool_suffix: str) -> int | None:
                return experiment_mappings.get(pool_suffix)

            unique_pools = pooling_table["pool"].unique()
            if len(unique_pools) > 1:
                for key, group in parsing.safe_groupby(pooling_table, "pool", PoolGroupKey):
                    pool_suffix = key.pool.strip().lower()
                    if pool_suffix in ("t", "skip"):
                        continue
                    if pool_suffix == "x":
                        for _, row in parsing.safe_iter(group, PooledLibraryRow):
                            library = session.get_one(Q.library.select(id=row.library_id))
                            library.status = C.LibraryStatus.FAILED
                            session.save(library)
                        continue

                    pool_suffix = str(key.pool).removeprefix(f"{lab_prep.name}_").strip()
                    pool = session.save(Q.pool.create(
                        name=f"{lab_prep.name}_{pool_suffix}",
                        pool_type=C.PoolType.INTERNAL,
                        contact_email=current_user.email,
                        contact_name=current_user.name,
                        owner_id=current_user.id,
                        lab_prep_id=lab_prep.id,
                        experiment_id=_experiment_id(pool_suffix),
                        clone_number=0,
                    ))
                    for _, row in parsing.safe_iter(group, PooledLibraryRow):
                        library = session.get_one(Q.library.select(id=row.library_id))
                        library.pool_id = pool.id
                        library.status = C.LibraryStatus.POOLED
                        session.save(library)

            elif len(unique_pools) > 0:
                pool = session.save(Q.pool.create(
                    name=lab_prep.name,
                    pool_type=C.PoolType.INTERNAL,
                    contact_email=current_user.email,
                    contact_name=current_user.name,
                    owner_id=current_user.id,
                    lab_prep_id=lab_prep.id,
                    experiment_id=_experiment_id("1"),
                    clone_number=0,
                ))
                for _, row in parsing.safe_iter(pooling_table, PooledLibraryRow):
                    library = session.get_one(Q.library.select(id=row.library_id))
                    library.pool_id = pool.id
                    library.status = C.LibraryStatus.POOLED
                    session.save(library)

            for seq_request_id in library_table["seq_request_id"].dropna().unique():
                seq_request = session.get_one(
                    Q.seq_request.select(id=int(seq_request_id)).options(
                        orm.selectinload(models.SeqRequest.libraries),
                    )
                )
                prepared = all(library.status.id >= C.LibraryStatus.POOLED.id for library in seq_request.libraries)
                if prepared and seq_request.status == C.SeqRequestStatus.ACCEPTED:
                    seq_request.status = C.SeqRequestStatus.PREPARED
                    session.save(seq_request)

            form.workflow.complete()
            return responses.htmx_response(
                redirect=responses.url_for("lab_prep_page", lab_prep_id=form.workflow.lab_prep_id),
                flash=responses.flash("Library pooling completed!", "success"),
            )
        return route
