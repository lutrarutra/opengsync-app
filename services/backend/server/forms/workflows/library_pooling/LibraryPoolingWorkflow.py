from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# from .. import library_pooling as wff


class LibraryPoolingWorkflow(HTMXWorkflow):
    def __init__(self, step: str, lab_prep_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.lab_prep_id = lab_prep_id

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "LibraryPoolingWorkflow" = Depends(LibraryPoolingWorkflow.Init(step)),
        ) -> "LibraryPoolingWorkflow":
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
            lab_prep_id: int,
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "LibraryPoolingWorkflow":
            return cls(uuid=uuid, r=r, lab_prep_id=lab_prep_id, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            lab_prep_id: int,
            user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            if (lab_prep := session.first(Q.lab_prep.select(id=lab_prep_id))) is None:
                raise exc.ItemNotFoundException()

            form = forms.LibraryPoolingForm(lab_prep=lab_prep, uuid=None, formdata=None)
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/library-pooling/{lab_prep_id}", tags=["library-pooling"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", LibraryPoolingWorkflow.Begin(), methods=["GET"], name="LibraryPoolingWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()