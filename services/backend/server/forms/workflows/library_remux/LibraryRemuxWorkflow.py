from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C
from opengsync_db.categories import LibraryStatus, MUXType

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc


class LibraryRemuxWorkflow(HTMXWorkflow):
    def __init__(self, step: str, library_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.library_id = library_id

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "LibraryRemuxWorkflow" = Depends(LibraryRemuxWorkflow.Init(step)),
        ) -> "LibraryRemuxWorkflow":
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
            library_id: int,
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "LibraryRemuxWorkflow":
            return cls(uuid=uuid, r=r, library_id=library_id, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            library_id: int,
            user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            if (library := session.first(Q.library.select(id=library_id))) is None:
                raise exc.ItemNotFoundException()

            access_level = session.get_access_level(Q.library.permissions(library.id, user.id))
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException()
            if library.status != LibraryStatus.DRAFT and access_level < C.AccessLevel.INSIDER:
                raise exc.NoPermissionsException()

            match library.mux_type:
                case MUXType.TENX_FLEX_PROBE:
                    return wff.FlexReMuxForm(library=library).make_response()
                case MUXType.TENX_OLIGO:
                    return wff.OligoReMuxForm(library=library).make_response()
                case MUXType.TENX_ABC_HASH:
                    return wff.OligoReMuxForm(library=library).make_response()
                case _:
                    raise exc.BadRequestException()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/library-remux/{library_id}", tags=["library-remux"])
        router.add_api_route("/begin", LibraryRemuxWorkflow.Begin(), methods=["GET"], name="LibraryRemuxWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()