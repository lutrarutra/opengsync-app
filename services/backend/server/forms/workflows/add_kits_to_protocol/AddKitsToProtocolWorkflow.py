from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# from .. import AddKitCombinationsForm


class AddKitsToProtocolWorkflow(HTMXWorkflow):
    def __init__(self, step: str, protocol_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.protocol_id = protocol_id

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "AddKitsToProtocolWorkflow" = Depends(AddKitsToProtocolWorkflow.Init(step)),
        ) -> "AddKitsToProtocolWorkflow":
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
            protocol_id: int,
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "AddKitsToProtocolWorkflow":
            return cls(uuid=uuid, r=r, protocol_id=protocol_id, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            protocol_id: int,
            user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            if (protocol := session.first(Q.protocol.select(id=protocol_id))) is None:
                raise exc.ItemNotFoundException()

            form = AddKitCombinationsFrom(formdata=None, protocol=protocol)
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/add-kits-to-protocol/{protocol_id}", tags=["add-kits-to-protocol"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", AddKitsToProtocolWorkflow.Begin(), methods=["GET"], name="AddKitsToProtocolWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()