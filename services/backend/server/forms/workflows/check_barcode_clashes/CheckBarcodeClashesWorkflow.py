from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# from opengsync_server.forms import SelectSamplesForm


class CheckBarcodeClashesWorkflow(HTMXWorkflow):
    def __init__(self, step: str, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "CheckBarcodeClashesWorkflow" = Depends(CheckBarcodeClashesWorkflow.Init(step)),
        ) -> "CheckBarcodeClashesWorkflow":
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
        ) -> "CheckBarcodeClashesWorkflow":
            return cls(uuid=uuid, r=r, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            user: models.User = Depends(dependencies.require_insider),
        ):
            form = SelectSamplesForm(
                workflow="check_barcode_clashes",
                select_lanes=True,
                select_pools=True,
                select_libraries=True,
            )
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/check-barcode-clashes", tags=["check-barcode-clashes"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", CheckBarcodeClashesWorkflow.Begin(), methods=["GET"], name="CheckBarcodeClashesWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()