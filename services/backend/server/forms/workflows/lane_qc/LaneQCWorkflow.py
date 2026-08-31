from typing import Self

from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, FormFunc
from .. import lane_qc as wf


class LaneQCWorkflowStep(HTMXWorkflowStep):
    workflow: "LaneQCWorkflow"

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="LaneQCWorkflow",
        ).include_query_params(uuid=self.workflow.uuid, **self.workflow._query_params)

    @classmethod
    def Init(cls: type[Self]) -> FormFunc:
        def dependency(
            workflow: LaneQCWorkflow = Depends(LaneQCWorkflow.Init(cls.__name__)),
        ) -> Self:
            return cls(workflow=workflow)
        return dependency

    @classmethod
    def Validate(cls: type[Self]) -> FormFunc:
        def dependency(
            form: Self = Depends(super(LaneQCWorkflowStep, cls).Validate()),
        ) -> Self:
            return form
        return dependency


class LaneQCWorkflow(HTMXWorkflow):
    def __init__(
        self,
        step: str,
        experiment_id: int,
        r: redis.RedisClient,
        uuid: str | None = None,
    ) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.experiment_id = experiment_id
        self._query_params: dict = {"experiment_id": experiment_id}

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            experiment_id: int = Query(..., description="Experiment ID"),
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            current_user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "LaneQCWorkflow":
            if session.first(Q.experiment.select(id=experiment_id)) is None:
                raise exc.NotFoundException("Experiment not found.")
            if not current_user.is_insider:
                raise exc.NoPermissionsException()
            return cls(step=step, experiment_id=experiment_id, r=r, uuid=uuid)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            workflow: LaneQCWorkflow = Depends(LaneQCWorkflow.Init("Begin")),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            experiment = session.get_one(Q.experiment.select(id=workflow.experiment_id))
            if experiment.workflow.combined_lanes:
                form = wf.UnifiedQCLanesForm.build(workflow, session)
            else:
                form = wf.QCLanesForm.build(workflow, session)
            return form.make_response()
        return route

    def get_next_step(self, form: "LaneQCWorkflowStep") -> "LaneQCWorkflowStep":
        raise NotImplementedError("Lane QC is a single-step workflow.")

    def complete_to_experiment(self, message: str = "Saved!"):
        next_url = responses.url_for("experiment_page", experiment_id=self.experiment_id)
        self.complete()
        return responses.htmx_response(
            redirect=next_url,
            flash=responses.flash(message, "success"),
        )

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(
            prefix="/lane-qc",
            tags=["lane-qc"],
            dependencies=[Depends(dependencies.require_insider)],
        )
        router.add_api_route(
            "/begin",
            LaneQCWorkflow.Begin(),
            methods=["GET"],
            name="LaneQCWorkflow.Begin",
        )
        router.include_router(wf.UnifiedQCLanesForm.Router(cls.__name__))
        router.include_router(wf.QCLanesForm.Router(cls.__name__))
        return router
