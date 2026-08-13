from fastapi import Depends, Response
from sqlalchemy import orm
import pandas as pd

from opengsync_db import SyncSession, models, categories as C

from ....core import dependencies, exceptions as exc
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from .MergePoolsWorkflow import MergePoolsWorkflowStep, MergePoolsWorkflow


class SelectSamplesForm(MergePoolsWorkflowStep):
    template_path = "workflows/merge_pools/select-samples.html"
    selected_pool_ids = inputs.tables.PoolSelectTableField(
        "Pools",
        "merge-pools",
        status_in=[
            C.PoolStatus.DRAFT,
            C.PoolStatus.SUBMITTED,
            C.PoolStatus.ACCEPTED,
            C.PoolStatus.STORED,
        ],
        required=True,
    )

    def __init__(self, workflow: MergePoolsWorkflow) -> None:
        super().__init__(workflow=workflow)
        if self.workflow.seq_request_id is not None:
            self.selected_pool_ids.query_params["seq_request_id"] = self.workflow.seq_request_id
        if self.workflow.lab_prep_id is not None:
            self.selected_pool_ids.query_params["lab_prep_id"] = self.workflow.lab_prep_id

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "SelectSamplesForm" = Depends(SelectSamplesForm.Init()),
        ) -> Response:
            pool_table = form.workflow.tables["pool_table"]
            form.selected_pool_ids.data = pool_table["pool_id"].unique().tolist()
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SelectSamplesForm" = Depends(SelectSamplesForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            pools = form.selected_pool_ids.get_selected_pools(session, options=[
                orm.selectinload(models.Pool.libraries),
            ])
            if len(pools) < 2:
                form.add_general_error("You must select at least 2 pools to merge.")
                raise exc.FormValidationException(form)

            pool_table_data: dict[str, list] = {
                "pool_id": [],
                "pool_name": [],
                "status_id": [],
            }
            library_dfs: list[pd.DataFrame] = []
            barcode_dfs: list[pd.DataFrame] = []

            for pool in pools:
                pool_table_data["pool_id"].append(pool.id)
                pool_table_data["pool_name"].append(pool.name)
                pool_table_data["status_id"].append(pool.status_id)
                library_dfs.append(session.pd.get_pool_libraries(pool.id))
                barcode_dfs.append(session.pd.get_pool_barcodes(pool.id))

            form.workflow.tables["pool_table"] = pd.DataFrame(pool_table_data)
            form.workflow.tables["library_table"] = pd.concat(library_dfs, ignore_index=True)
            form.workflow.tables["barcode_table"] = pd.concat(barcode_dfs, ignore_index=True)
            return form.workflow.get_next_step(form).make_response()
        return route
