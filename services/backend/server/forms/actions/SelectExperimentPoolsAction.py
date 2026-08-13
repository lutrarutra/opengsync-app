from fastapi import Depends, Response

from opengsync_db import models, queries as Q, SyncSession, categories as C, actions

from ...core import dependencies, responses, exceptions as exc
from ...components import inputs
from ..HTMXForm import RouteFunc, htmx_route, HTMXForm, FormFunc


class SelectExperimentPoolsAction(HTMXForm):
    template_path = "actions/select-experiment-pools.html"
    selected_pool_ids = inputs.tables.PoolSelectTableField(
        "Pools",
        "select-experiment-pools",
        status_in=[C.PoolStatus.STORED],
        required=False,
    )

    def __init__(self, experiment: models.Experiment) -> None:
        super().__init__()
        self.experiment = experiment
        self.experiment_id = experiment.id
        self._context["experiment"] = experiment

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            experiment_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.require_insider),
        ) -> "SelectExperimentPoolsAction":
            if (experiment := session.first(Q.experiment.select(id=experiment_id))) is None:
                raise exc.ItemNotFoundException()
            return cls(experiment=experiment)
        return dependency

    @htmx_route("GET", "/{experiment_id}/select-pools", name="Begin")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "SelectExperimentPoolsAction" = Depends(SelectExperimentPoolsAction.Init()),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}/select-pools", name="Submit")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SelectExperimentPoolsAction" = Depends(SelectExperimentPoolsAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            experiment = session.get_one(Q.experiment.select(id=form.experiment_id))

            for pool in form.selected_pool_ids.get_selected_pools(session):
                if pool.experiment_id == experiment.id:
                    continue
                actions.link_pool_experiment(session, experiment=experiment, pool=pool)

            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=experiment.id),
                flash=responses.flash("Pools linked to experiment", "success"),
            )
        return route
