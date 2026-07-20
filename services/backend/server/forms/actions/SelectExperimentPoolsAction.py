from fastapi import Depends, Response, Query

from opengsync_db import categories as C, SyncSession, queries as Q, actions

from ...core import dependencies, responses, exceptions as exc
from ...components import inputs
from ..HTMXForm import RouteFunc, htmx_route, HTMXForm


class SelectExperimentPoolsAction(HTMXForm):
    template_path = "actions/store-samples.html"
    selected_pool_ids = inputs.tables.PoolSelectTableField(
        "Pools",
        "store-samples",
        status_in=[C.PoolStatus.STORED],
        required=False
    )

    @htmx_route("GET", "/{experiment_id}")
    def Begin(cls) -> RouteFunc:
        def route(
            experiment_id: int,
            form: "SelectExperimentPoolsAction" = Depends(SelectExperimentPoolsAction.Init()),
        ):
            if experiment_id is not None:
                form.selected_pool_ids.query_params["ex_experiment_id"] = experiment_id
            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}")
    def Submit(cls) -> RouteFunc:
        def route(
            experiment_id: int,
            form: "SelectExperimentPoolsAction" = Depends(SelectExperimentPoolsAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _ = Depends(dependencies.require_insider),
        ) -> Response:
            experiment = session.get_one(Q.experiment.select(id=experiment_id))
            
            for pool in form.selected_pool_ids.get_selected_pools(session):
                if pool.experiment_id is not None:
                    raise exc.BadRequestException(f"Pool {pool.name} is already linked to experiment")
                actions.link_pool_experiment(session, experiment=experiment, pool=pool)

            return responses.htmx_response(
                redirect=responses.url_for("dashboard"),
                flash=responses.flash(f"Pools added to the experiment!", "success")
            )
        return route