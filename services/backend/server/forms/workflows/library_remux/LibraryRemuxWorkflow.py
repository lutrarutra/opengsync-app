from typing import Self

from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C
from opengsync_db.categories import LibraryStatus, MUXType

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, FormFunc
from .. import library_remux as wf


class LibraryRemuxWorkflowStep(HTMXWorkflowStep):
    workflow: "LibraryRemuxWorkflow"

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="LibraryRemuxWorkflow",
        ).include_query_params(uuid=self.workflow.uuid, **self.workflow._query_params)

    @classmethod
    def Init(cls: type[Self]) -> FormFunc:
        def dependency(
            workflow: LibraryRemuxWorkflow = Depends(LibraryRemuxWorkflow.Init(cls.__name__)),
        ) -> Self:
            return cls(workflow=workflow)
        return dependency

    @classmethod
    def Validate(cls: type[Self]) -> FormFunc:
        def dependency(
            form: Self = Depends(super(LibraryRemuxWorkflowStep, cls).Validate()),
        ) -> Self:
            return form
        return dependency


class LibraryRemuxWorkflow(HTMXWorkflow):
    def __init__(
        self,
        step: str,
        library_id: int,
        r: redis.RedisClient,
        uuid: str | None = None,
    ) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.library_id = library_id
        self._query_params: dict = {"library_id": library_id}

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            library_id: int = Query(..., description="Library ID"),
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "LibraryRemuxWorkflow":
            library = session.first(Q.library.select(id=library_id))
            if library is None:
                raise exc.NotFoundException("Library not found.")

            access_level = session.get_access_level(Q.library.permissions(library.id, user.id))
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException()
            if library.status != LibraryStatus.DRAFT and access_level < C.AccessLevel.INSIDER:
                raise exc.NoPermissionsException()

            return cls(step=step, library_id=library_id, r=r, uuid=uuid)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            workflow: LibraryRemuxWorkflow = Depends(LibraryRemuxWorkflow.Init("Begin")),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            library = session.get_one(Q.library.select(id=workflow.library_id))
            match library.mux_type:
                case MUXType.TENX_FLEX_PROBE:
                    form = wf.FlexReMuxForm.build(workflow, session)
                case MUXType.TENX_OLIGO:
                    form = wf.OligoReMuxForm.build(workflow, session)
                case MUXType.TENX_ABC_HASH:
                    form = wf.OligoReMuxForm.build(workflow, session)
                case _:
                    raise exc.BadRequestException()
            return form.make_response()
        return route

    def get_next_step(self, form: "LibraryRemuxWorkflowStep") -> "LibraryRemuxWorkflowStep":
        raise NotImplementedError("Library Remux is a single-step workflow.")

    def complete_to_library(self, tab: str | None = None, message: str = "Changes saved!"):
        next_url = responses.url_for("library_page", library_id=self.library_id)
        if tab is not None:
            next_url = next_url.include_query_params(tab=tab)
        self.complete()
        return responses.htmx_response(
            redirect=next_url,
            flash=responses.flash(message, "success"),
        )

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/library-remux", tags=["library-remux"])
        router.add_api_route("/begin", LibraryRemuxWorkflow.Begin(), methods=["GET"], name="LibraryRemuxWorkflow.Begin")
        router.include_router(wf.FlexReMuxForm.Router(cls.__name__))
        router.include_router(wf.OligoReMuxForm.Router(cls.__name__))
        return router
