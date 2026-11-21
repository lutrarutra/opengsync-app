from fastapi import Depends, Response
from sqlalchemy import orm
import pandas as pd
from pydantic import BaseModel

from opengsync_db import models, queries as Q, SyncSession, categories as C, actions
from opengsync_db.transitions import run_operation, lab as lab_ops

from opengsync_db.core.blueprints import pd_transforms as T

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

    def prepare_context(self) -> None:
        session = ctx.session
        self.lab_prep = session.get_one(Q.lab_prep.select(id=self.workflow.lab_prep_id))
        pooling_table = self.workflow.tables["pooling_table"]
        barcode_table = T.lab_prep_barcodes(
            session.get_pandas(
                Q.pd.lab_prep_barcodes(self.workflow.lab_prep_id),
                limit=None,
            )
        )
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
            current_user: models.User = Depends(dependencies.require_insider),
            form: CompleteLibraryPoolingForm = Depends(CompleteLibraryPoolingForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            lab_prep = session.get_one(
                Q.lab_prep.select(id=form.workflow.lab_prep_id).options(
                    orm.selectinload(models.LabPrep.pools),
                )
            )
            pooling_table = form.workflow.tables["pooling_table"].copy()
            library_table = form.workflow.tables["library_table"]

            with run_operation(session, lab_ops.POOL_LIBRARIES, subject=lab_prep):
                pooling_table["old_pool_id"] = parsing.map_columns(pooling_table, library_table, "library_id", "pool_id")
                pooling_table["experiment_id"] = None

                for pool in lab_prep.pools:
                    pooling_table.loc[pooling_table["old_pool_id"] == pool.id, "experiment_id"] = pool.experiment_id
                    # Unpool first: deleting the pool would only null pool_id and leave the experiment behind
                    for library in list(pool.libraries):
                        actions.set_library_pool(session, library, None)
                    session.delete(pool)

                def _pool_name(value: str) -> str:
                    # the given name is used as "{prep}_{value}"; the prep name itself
                    # (also filled in when no pool was given) names the pool after the prep
                    suffix = str(value).strip().removeprefix(f"{lab_prep.name}_").strip()
                    if not suffix or suffix == lab_prep.name:
                        return lab_prep.name
                    return f"{lab_prep.name}_{suffix}"

                def _num_m_reads_requested(group: pd.DataFrame) -> float | None:
                    # per library in the pooling step; the pool requests the total
                    values = group["num_m_reads_requested"].dropna()
                    return float(values.sum()) if not values.empty else None

                for key, group in parsing.safe_groupby(pooling_table, PoolGroupKey):
                    # x (failed), t (control) and skip are not pools
                    pool_value = key.pool.strip().lower()
                    if pool_value in ("t", "skip"):
                        continue
                    if pool_value == "x":
                        for _, row in parsing.safe_iter(group, PooledLibraryRow):
                            library = session.get_one(Q.library.select(id=row.library_id))
                            library.status = C.LibraryStatus.FAILED
                            session.save(library)
                        continue

                    # keep the experiment of the old pool if all of the group's libraries shared it
                    experiment_ids = group["experiment_id"].unique()
                    experiment_id = int(experiment_ids[0]) if len(experiment_ids) == 1 and pd.notna(experiment_ids[0]) else None

                    pool = session.save(Q.pool.create(
                        name=_pool_name(key.pool),
                        pool_type=C.PoolType.INTERNAL,
                        contact_email=current_user.email,
                        contact_name=current_user.name,
                        owner_id=current_user.id,
                        lab_prep_id=lab_prep.id,
                        experiment_id=experiment_id,
                        num_m_reads_requested=_num_m_reads_requested(group),
                        clone_number=0,
                    ))
                    for _, row in parsing.safe_iter(group, PooledLibraryRow):
                        library = session.get_one(Q.library.select(id=row.library_id))
                        actions.set_library_pool(session, library, pool)
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
