from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# from .. import lane_pools as wff


class LanePoolsWorkflow(HTMXWorkflow):
    def __init__(self, step: str, experiment_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.experiment_id = experiment_id

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "LanePoolsWorkflow" = Depends(LanePoolsWorkflow.Init(step)),
        ) -> "LanePoolsWorkflow":
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
        ) -> "LanePoolsWorkflow":
            return cls(uuid=uuid, r=r, experiment_id=experiment_id, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            experiment_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ):
            if (experiment := session.first(Q.experiment.select(id=experiment_id))) is None:
                raise exc.ItemNotFoundException()

            if experiment.workflow.combined_lanes:
                form = wff.UnifiedLanePoolingForm(experiment=experiment)
            else:
                form = wff.LanePoolingForm(experiment=experiment)
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/lane-pools/{experiment_id}", tags=["lane-pools"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", LanePoolsWorkflow.Begin(), methods=["GET"], name="LanePoolsWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()