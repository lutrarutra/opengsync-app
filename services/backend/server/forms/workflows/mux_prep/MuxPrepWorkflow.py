from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C
from opengsync_db.categories import MUXType

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
from .. import mux_prep as wff


class MuxPrepWorkflow(HTMXWorkflow):
    def __init__(self, step: str, lab_prep_id: int, mux_type_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.lab_prep_id = lab_prep_id
        self.mux_type_id = mux_type_id

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "MuxPrepWorkflow" = Depends(MuxPrepWorkflow.Init(step)),
        ) -> "MuxPrepWorkflow":
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
            mux_type_id: int,
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "MuxPrepWorkflow":
            return cls(uuid=uuid, r=r, lab_prep_id=lab_prep_id, mux_type_id=mux_type_id, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            lab_prep_id: int,
            mux_type_id: int,
            user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            if not (mux_type := MUXType.get(mux_type_id)):
                raise exc.BadRequestException()

            if (lab_prep := session.first(Q.lab_prep.select(id=lab_prep_id))) is None:
                raise exc.ItemNotFoundException()

            if mux_type == MUXType.TENX_OLIGO:
                form = wff.OligoMuxForm(lab_prep=lab_prep)
            elif mux_type == MUXType.TENX_FLEX_PROBE:
                form = wff.FlexMuxForm(lab_prep=lab_prep)
            elif mux_type == MUXType.TENX_ON_CHIP:
                form = wff.OCMMuxForm(lab_prep=lab_prep)
            else:
                raise NotImplementedError(f"Multiplexing type {mux_type} is not implemented.")

            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/mux-prep/{lab_prep_id}/{mux_type_id}", tags=["mux-prep"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", MuxPrepWorkflow.Begin(), methods=["GET"], name="MuxPrepWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()