from typing import Self

from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, FormFunc
from .. import share_project_data as wf


class ShareProjectDataWorkflowStep(HTMXWorkflowStep):
    workflow: "ShareProjectDataWorkflow"

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="ShareProjectDataWorkflow",
        ).include_query_params(uuid=self.workflow.uuid, **self.workflow._query_params)

    @classmethod
    def Init(cls: type[Self]) -> FormFunc:
        def dependency(
            workflow: ShareProjectDataWorkflow = Depends(ShareProjectDataWorkflow.Init(cls.__name__)),
        ) -> Self:
            return cls(workflow=workflow)
        return dependency

    @classmethod
    def Validate(cls: type[Self]) -> FormFunc:
        def dependency(
            form: Self = Depends(super(ShareProjectDataWorkflowStep, cls).Validate()),
        ) -> Self:
            return form
        return dependency


class ShareProjectDataWorkflow(HTMXWorkflow):
    def __init__(
        self,
        step: str,
        project_id: int,
        r: redis.RedisClient,
        uuid: str | None = None,
    ) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.project_id = project_id
        self._query_params: dict = {"project_id": project_id}

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            project_id: int = Query(..., description="Project ID"),
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            viewer_id: int = Depends(dependencies.require_user_id),
            session: SyncSession = Depends(dependencies.db_session),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "ShareProjectDataWorkflow":
            project = session.first(Q.project.select(id=project_id))
            if project is None:
                raise exc.NotFoundException("Project not found.")

            access_level = session.get_access_level(Q.project.permissions(project.id, viewer_id))
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException()

            return cls(step=step, project_id=project_id, r=r, uuid=uuid)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            workflow: ShareProjectDataWorkflow = Depends(ShareProjectDataWorkflow.Init("Begin")),
            _: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            form = wf.ShareProjectDataForm.build(workflow, session)
            return form.make_response()
        return route

    def get_next_step(self, form: "ShareProjectDataWorkflowStep") -> "ShareProjectDataWorkflowStep":
        raise NotImplementedError("Share Project Data is a single-step workflow.")

    def complete_to_project(self, message: str = "Data Share Email Sent!"):
        next_url = responses.url_for("project_page", project_id=self.project_id).include_query_params(
            tab="project-data_paths-tab",
        )
        self.complete()
        return responses.htmx_response(
            redirect=next_url,
            flash=responses.flash(message, "success"),
        )

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/share-project-data", tags=["share-project-data"])
        router.add_api_route(
            "/begin",
            ShareProjectDataWorkflow.Begin(),
            methods=["GET"],
            name="ShareProjectDataWorkflow.Begin",
        )
        router.include_router(wf.ShareProjectDataForm.Router(cls.__name__))
        return router
