from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C
from opengsync_db.categories import PoolStatus

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# from opengsync_server.forms import SelectSamplesForm


class MergePoolsWorkflow(HTMXWorkflow):
    def __init__(self, step: str, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "MergePoolsWorkflow" = Depends(MergePoolsWorkflow.Init(step)),
        ) -> "MergePoolsWorkflow":
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
        ) -> "MergePoolsWorkflow":
            return cls(uuid=uuid, r=r, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
            seq_request_id: int | None = Query(None),
            lab_prep_id: int | None = Query(None),
        ):
            context: dict = {}
            if seq_request_id is not None:
                seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))
                if session.get_access_level(Q.seq_request.permissions(seq_request.id, user.id)) < C.AccessLevel.WRITE:
                    raise exc.NoPermissionsException()
                context["seq_request"] = seq_request
            elif lab_prep_id is not None:
                lab_prep = session.get_one(Q.lab_prep.select(id=lab_prep_id))
                context["lab_prep"] = lab_prep

            if not user.is_insider():
                if "seq_request" not in context:
                    raise exc.NoPermissionsException()

            form = SelectSamplesForm(
                "merge_pools",
                context=context,
                select_pools=True,
                pool_status_filter=[
                    PoolStatus.DRAFT,
                    PoolStatus.SUBMITTED,
                    PoolStatus.ACCEPTED,
                    PoolStatus.STORED,
                ]
            )
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/merge-pools", tags=["merge-pools"])
        router.add_api_route("/begin", MergePoolsWorkflow.Begin(), methods=["GET"], name="MergePoolsWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()