from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C
from opengsync_db.categories import LibraryStatus

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# from opengsync_server.forms import SelectSamplesForm


class SelectPoolLibrariesWorkflow(HTMXWorkflow):
    def __init__(self, step: str, pool_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.pool_id = pool_id

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "SelectPoolLibrariesWorkflow" = Depends(SelectPoolLibrariesWorkflow.Init(step)),
        ) -> "SelectPoolLibrariesWorkflow":
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
            pool_id: int,
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "SelectPoolLibrariesWorkflow":
            return cls(uuid=uuid, r=r, pool_id=pool_id, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            pool_id: int,
            user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            if (pool := session.first(Q.pool.select(id=pool_id))) is None:
                raise exc.ItemNotFoundException()

            form = SelectSamplesForm(
                "select_pool_libraries",
                select_libraries=True,
                context={"pool": pool},
                library_status_filter=[
                    LibraryStatus.DRAFT,
                    LibraryStatus.SUBMITTED,
                    LibraryStatus.ACCEPTED,
                    LibraryStatus.PREPARING,
                    LibraryStatus.STORED,
                ]
            )
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/select-pool-libraries/{pool_id}", tags=["select-pool-libraries"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", SelectPoolLibrariesWorkflow.Begin(), methods=["GET"], name="SelectPoolLibrariesWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()