from typing import Self

from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, FormFunc
from .. import library_pooling as wf


class LibraryPoolingWorkflowStep(HTMXWorkflowStep):
    workflow: "LibraryPoolingWorkflow"

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="LibraryPoolingWorkflow",
        ).include_query_params(uuid=self.workflow.uuid, **self.workflow._query_params)

    @classmethod
    def Init(cls: type[Self]) -> FormFunc:
        def dependency(
            workflow: LibraryPoolingWorkflow = Depends(LibraryPoolingWorkflow.Init(cls.__name__)),
        ) -> Self:
            return cls(workflow=workflow)
        return dependency

    @classmethod
    def Validate(cls: type[Self]) -> FormFunc:
        def dependency(
            form: Self = Depends(super(LibraryPoolingWorkflowStep, cls).Validate()),
        ) -> Self:
            return form
        return dependency


class LibraryPoolingWorkflow(HTMXWorkflow):
    def __init__(
        self,
        step: str,
        lab_prep_id: int,
        r: redis.RedisClient,
        uuid: str | None = None,
    ) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.lab_prep_id = lab_prep_id
        self._query_params: dict = {"lab_prep_id": lab_prep_id}

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            lab_prep_id: int = Query(..., description="Lab Prep ID"),
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            current_user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "LibraryPoolingWorkflow":
            if session.first(Q.lab_prep.select(id=lab_prep_id)) is None:
                raise exc.ItemNotFoundException("Lab prep not found.")
            if not current_user.is_insider:
                raise exc.NoPermissionsException()
            return cls(step=step, lab_prep_id=lab_prep_id, r=r, uuid=uuid)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            form: wf.LibraryPoolingForm = Depends(wf.LibraryPoolingForm.Init()),
        ):
            return form.make_response(flash=form._context.pop("flash", None))
        return route

    def get_next_step(self, form: "LibraryPoolingWorkflowStep") -> "LibraryPoolingWorkflowStep":
        self.add_step(form.__class__.__name__)
        match form.__class__:
            case wf.LibraryPoolingForm:
                next_form = wf.CompleteLibraryPoolingForm(workflow=self)
            case _:
                raise exc.OpeNGSyncServerException(
                    f"Unknown form class {form.__class__.__name__} in LibraryPoolingWorkflow."
                )

        self.previous_url = responses.url_for(
            f"{self.__class__.__name__}.{form.__class__.__name__}.Previous",
        ).include_query_params(uuid=self.uuid, **self._query_params)
        self.add_step(next_form.__class__.__name__)
        return next_form

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(
            prefix="/library-pooling",
            tags=["library-pooling"],
            dependencies=[Depends(dependencies.require_insider)],
        )
        router.add_api_route("/begin", LibraryPoolingWorkflow.Begin(), methods=["GET"], name="LibraryPoolingWorkflow.Begin")
        router.include_router(wf.LibraryPoolingForm.Router(cls.__name__))
        router.include_router(wf.CompleteLibraryPoolingForm.Router(cls.__name__))
        return router
