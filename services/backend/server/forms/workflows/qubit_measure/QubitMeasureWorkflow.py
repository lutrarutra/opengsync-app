from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C
from opengsync_db.categories import PoolStatus, LibraryStatus, SampleStatus

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# from opengsync_server.forms import SelectSamplesForm


class QubitMeasureWorkflow(HTMXWorkflow):
    def __init__(self, step: str, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "QubitMeasureWorkflow" = Depends(QubitMeasureWorkflow.Init(step)),
        ) -> "QubitMeasureWorkflow":
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
        ) -> "QubitMeasureWorkflow":
            return cls(uuid=uuid, r=r, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
            entity: str | None = Query(None),
            seq_request_id: int | None = Query(None),
            experiment_id: int | None = Query(None),
            pool_id: int | None = Query(None),
        ):
            context = {}
            if seq_request_id is not None:
                if (seq_request := session.first(Q.seq_request.select(id=seq_request_id))) is None:
                    raise exc.ItemNotFoundException()
                context["seq_request"] = seq_request
            if experiment_id is not None:
                if (experiment := session.first(Q.experiment.select(id=experiment_id))) is None:
                    raise exc.ItemNotFoundException()
                context["experiment"] = experiment
            if pool_id is not None:
                if (pool := session.first(Q.pool.select(id=pool_id))) is None:
                    raise exc.ItemNotFoundException()
                context["pool"] = pool

            form = SelectSamplesForm(
                workflow="qubit_measure", context=context,
                sample_status_filter=[SampleStatus.STORED],
                library_status_filter=[LibraryStatus.PREPARING],
                pool_status_filter=[PoolStatus.STORED],
                select_lanes=True if entity is None or entity == "lane" else False,
                select_pools=True if entity is None or entity == "pool" else False,
                select_libraries=True if entity is None or entity == "library" else False,
                select_samples=True if entity is None or entity == "sample" else False,
            )
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/qubit-measure", tags=["qubit-measure"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", QubitMeasureWorkflow.Begin(), methods=["GET"], name="QubitMeasureWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()