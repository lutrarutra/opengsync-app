from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# from ...share import ShareProjectDataForm


class ShareProjectDataWorkflow(HTMXWorkflow):
    def __init__(self, step: str, project_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.project_id = project_id

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "ShareProjectDataWorkflow" = Depends(ShareProjectDataWorkflow.Init(step)),
        ) -> "ShareProjectDataWorkflow":
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
            project_id: int,
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "ShareProjectDataWorkflow":
            return cls(uuid=uuid, r=r, project_id=project_id, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            project_id: int,
            user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            if (project := session.first(Q.project.select(id=project_id))) is None:
                raise exc.ItemNotFoundException()

            access_level = session.get_access_level(Q.project.permissions(project.id, user.id))
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException()

            form = ShareProjectDataForm(project)
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/share-project-data/{project_id}", tags=["share-project-data"])
        router.add_api_route("/begin", ShareProjectDataWorkflow.Begin(), methods=["GET"], name="ShareProjectDataWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()