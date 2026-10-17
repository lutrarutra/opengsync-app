from typing import Self

from fastapi import APIRouter, Depends, Query

from opengsync_db import models, queries as Q, SyncSession

from ....core import dependencies, exceptions as exc, redis, responses
from ....core.context import ctx
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import FormFunc, RouteFunc
from .. import split_project as wf


class SplitProjectWorkflowStep(HTMXWorkflowStep):
    workflow: "SplitProjectWorkflow"

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="SplitProjectWorkflow",
        ).include_query_params(uuid=self.workflow.uuid, **self.workflow._query_params)

    @classmethod
    def Init(cls: type[Self]) -> FormFunc:
        def dependency(
            workflow: SplitProjectWorkflow = Depends(SplitProjectWorkflow.Init(cls.__name__)),
        ) -> Self:
            return cls(workflow=workflow)
        return dependency

    @classmethod
    def Validate(cls: type[Self]) -> FormFunc:
        def dependency(
            form: Self = Depends(super(SplitProjectWorkflowStep, cls).Validate()),
        ) -> Self:
            return form
        return dependency


class SplitProjectWorkflow(HTMXWorkflow):
    def __init__(
        self,
        step: str,
        project_id: int,
        r: redis.RedisClient,
        uuid: str | None = None,
    ) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.project_id = project_id
        self._query_params: dict[str, int] = {"project_id": project_id}

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            project_id: int = Query(..., description="Source project ID"),
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            current_user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "SplitProjectWorkflow":
            if session.first(Q.project.select(id=project_id)) is None:
                raise exc.NotFoundException("Project not found.")
            return cls(step=step, project_id=project_id, r=r, uuid=uuid)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            workflow: "SplitProjectWorkflow" = Depends(cls.Init("Begin")),
        ):
            form = wf.SelectSamplesForm(workflow=workflow)
            return form.make_response()
        return route

    def get_next_step(self, form: "SplitProjectWorkflowStep") -> "SplitProjectWorkflowStep":
        self.add_step(form.__class__.__name__)
        match form.__class__:
            case wf.SelectSamplesForm:
                next_form = wf.ProjectSelectForm(workflow=self)
            case wf.ProjectSelectForm:
                next_form = wf.ConfirmSplitForm.build(self, ctx.session)
            case _:
                raise exc.OpeNGSyncServerException(
                    f"Unknown form class {form.__class__.__name__} in SplitProjectWorkflow."
                )

        self.previous_url = responses.url_for(
            f"{self.__class__.__name__}.{form.__class__.__name__}.Previous",
        ).include_query_params(uuid=self.uuid, **self._query_params)
        self.add_step(next_form.__class__.__name__)
        return next_form

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(
            prefix="/split-project",
            tags=["split-project"],
            dependencies=[Depends(dependencies.require_insider)],
        )
        router.add_api_route(
            "/begin",
            SplitProjectWorkflow.Begin(),
            methods=["GET"],
            name="SplitProjectWorkflow.Begin",
        )
        router.include_router(wf.SelectSamplesForm.Router(cls.__name__))
        router.include_router(wf.ProjectSelectForm.Router(cls.__name__))
        router.include_router(wf.ConfirmSplitForm.Router(cls.__name__))
        return router
