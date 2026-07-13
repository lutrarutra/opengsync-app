from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# from opengsync_server.forms import SelectSamplesForm


class RelibWorkflow(HTMXWorkflow):
    def __init__(self, step: str, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "RelibWorkflow" = Depends(RelibWorkflow.Init(step)),
        ) -> "RelibWorkflow":
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
        ) -> "RelibWorkflow":
            return cls(uuid=uuid, r=r, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
            seq_request_id: int | None = Query(None),
            lab_prep_id: int | None = Query(None),
        ):
            context: dict = {}
            if seq_request_id is not None:
                if (seq_request := session.first(Q.seq_request.select(id=seq_request_id))) is None:
                    raise exc.ItemNotFoundException()
                context["seq_request"] = seq_request
            elif lab_prep_id is not None:
                if (lab_prep := session.first(Q.lab_prep.select(id=lab_prep_id))) is None:
                    raise exc.ItemNotFoundException()
                context["lab_prep"] = lab_prep

            form = SelectSamplesForm("relib", context=context, select_libraries=True)
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/relib", tags=["relib"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", RelibWorkflow.Begin(), methods=["GET"], name="RelibWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()