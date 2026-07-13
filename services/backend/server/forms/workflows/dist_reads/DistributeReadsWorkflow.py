from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# from .. import dist_reads as wff


class DistributeReadsWorkflow(HTMXWorkflow):
    def __init__(self, step: str, experiment_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.experiment_id = experiment_id

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "DistributeReadsWorkflow" = Depends(DistributeReadsWorkflow.Init(step)),
        ) -> "DistributeReadsWorkflow":
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
        ) -> "DistributeReadsWorkflow":
            return cls(uuid=uuid, r=r, experiment_id=experiment_id, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            experiment_id: int,
            user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            if (experiment := session.first(Q.experiment.select(id=experiment_id))) is None:
                raise exc.ItemNotFoundException()

            if experiment.workflow.combined_lanes:
                form = wff.DistributeReadsCombinedForm(experiment=experiment, current_user=user)
            else:
                form = wff.DistributeReadsSeparateForm(experiment=experiment, current_user=user)
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/distribute-reads/{experiment_id}", tags=["distribute-reads"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", DistributeReadsWorkflow.Begin(), methods=["GET"], name="DistributeReadsWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()