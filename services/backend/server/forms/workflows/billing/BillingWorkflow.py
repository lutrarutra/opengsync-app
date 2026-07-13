from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# from ...billing import SelectExperimentsForm


class BillingWorkflow(HTMXWorkflow):
    def __init__(self, step: str, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "BillingWorkflow" = Depends(BillingWorkflow.Init(step)),
        ) -> "BillingWorkflow":
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
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "BillingWorkflow":
            return cls(uuid=uuid, r=r, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            user: models.User = Depends(dependencies.require_insider),
        ):
            return SelectExperimentsForm().make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/billing", tags=["billing"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", BillingWorkflow.Begin(), methods=["GET"], name="BillingWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()