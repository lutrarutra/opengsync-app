from fastapi import Query, Depends, APIRouter
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# # from opengsync_server.forms import SelectSamplesForm


class SelectExperimentPoolsWorkflow(HTMXWorkflow):
    def __init__(self, step: str, experiment_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.experiment_id = experiment_id

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "SelectExperimentPoolsWorkflow" = Depends(SelectExperimentPoolsWorkflow.Init(step)),
        ) -> "SelectExperimentPoolsWorkflow":
            if workflow.pop_step() is None:
                raise exc.OpeNGSyncServerException("No previous step found in the workflow.")
            if (current := workflow.step_tracker.last()) is None:
                raise exc.OpeNGSyncServerException("No previous step found in the workflow.")
            workflow.init_step(current)
            return workflow
        return dependency

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            experiment_id: int,
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "SelectExperimentPoolsWorkflow":
            return cls(uuid=uuid, r=r, experiment_id=experiment_id, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            experiment_id: int,
            user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            if (experiment := session.first(
                Q.experiment.select(id=experiment_id),
                options=orm.selectinload(models.Experiment.pools),
            )) is None:
                raise exc.ItemNotFoundException()

            context = {"experiment": experiment}
            form = SelectSamplesForm.create_workflow_form(workflow="select_experiment_pools", context=context)
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/select-experiment-pools/{experiment_id}", tags=["select-experiment-pools"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", SelectExperimentPoolsWorkflow.Begin(), methods=["GET"], name="SelectExperimentPoolsWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()