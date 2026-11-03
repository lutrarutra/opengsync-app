from typing import Self

import pandas as pd
from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, categories as C, SyncSession
from opengsync_db.models.SampleSubmissionLayout import DeliverableKind

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ..library_annotation.LibraryAnnotationWorkflow import require_seq_request_write
from ...HTMXForm import RouteFunc, FormFunc
from .. import sample_submission_layout as wf

EXPIRED = "This submission layout has expired. Please start again."

KIND_LABELS: dict[DeliverableKind, str] = {"sample": "Sample", "library": "Library", "pool": "Pool"}


def deliverables(session: SyncSession, seq_request_id: int, kind: DeliverableKind) -> list[tuple[int, str]]:
    """(id, name) of the samples, libraries or pools of the request that are handed in."""
    match kind:
        case "sample":
            stmt = Q.sample.select(seq_request_id=seq_request_id).order_by(models.Sample.id)
        case "library":
            stmt = Q.library.select(seq_request_id=seq_request_id).order_by(models.Library.id)
        case "pool":
            stmt = Q.pool.select(seq_request_id=seq_request_id).order_by(models.Pool.id)
    return [(item.id, item.name) for item in session.get_all(stmt, limit=None)]


def default_kind(submission_type: C.SubmissionType) -> DeliverableKind:
    match submission_type:
        case C.SubmissionType.POOLED_LIBRARIES:
            return "pool"
        case C.SubmissionType.UNPOOLED_LIBRARIES:
            return "library"
        case _:
            return "sample"


class SampleSubmissionLayoutWorkflowStep(HTMXWorkflowStep):
    workflow: "SampleSubmissionLayoutWorkflow"

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="SampleSubmissionLayoutWorkflow",
            seq_request_id=self.workflow.seq_request_id,
        ).include_query_params(uuid=self.workflow.uuid)

    @classmethod
    def Init(cls: type[Self]) -> FormFunc:
        def dependency(
            workflow: SampleSubmissionLayoutWorkflow = Depends(SampleSubmissionLayoutWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Self:
            return cls(workflow=workflow, session=session)
        return dependency

    @classmethod
    def Validate(cls: type[Self]) -> FormFunc:
        def dependency(
            form: Self = Depends(super(SampleSubmissionLayoutWorkflowStep, cls).Validate()),
        ) -> Self:
            return form
        return dependency


class SampleSubmissionLayoutWorkflow(HTMXWorkflow):
    def __init__(self, step: str, seq_request_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.seq_request_id = seq_request_id

    @property
    def layout_type(self) -> C.SubmissionLayoutType:
        return C.SubmissionLayoutType.get(self.metadata["layout_type_id"])

    @property
    def kind(self) -> DeliverableKind:
        return self.metadata["kind"]

    def authorize(self, step: str) -> None:
        # The state is keyed by UUID only, so a run must stay bound to the request it was started for.
        if step == wf.SelectLayoutTypeForm.__name__:
            return
        if step not in self.step_tracker.steps or self.header.get("seq_request_id") is None:
            raise exc.BadRequestException(EXPIRED)
        if self.header.get("seq_request_id") != self.seq_request_id:
            raise exc.BadRequestException("This submission layout belongs to another sequencing request.")

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            seq_request_id: int,
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "SampleSubmissionLayoutWorkflow":
            workflow = cls(step=step, seq_request_id=seq_request_id, r=r, uuid=uuid)
            workflow.authorize(step)
            return workflow
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            form: wf.SelectLayoutTypeForm = Depends(wf.SelectLayoutTypeForm.Init()),
        ):
            return form.make_response()
        return route

    def build_layout_table(self, session: SyncSession) -> pd.DataFrame:
        """One row per deliverable, with the position of the saved layout if it is of the same type and kind."""
        seq_request = session.get_one(Q.seq_request.select(id=self.seq_request_id))
        saved: dict[int, models.SampleSubmissionLayout] = {}
        if seq_request.submission_layout_type == self.layout_type:
            saved = {
                entry.sample_id or entry.library_id or entry.pool_id: entry  # type: ignore[misc]
                for entry in seq_request.submission_layout if entry.kind == self.kind
            }
        items = deliverables(session, self.seq_request_id, self.kind)
        # Tubes without a saved position are assumed to be labelled with the item name
        is_tubes = self.layout_type == C.SubmissionLayoutType.TUBES
        return pd.DataFrame({
            "item_id": [item_id for item_id, _ in items],
            "name": [name for _, name in items],
            "set_name": [(saved[item_id].set_name or None) if item_id in saved else None for item_id, _ in items],
            "position": [
                saved[item_id].position if item_id in saved else (name if is_tubes else None)
                for item_id, name in items
            ],
        })

    def get_next_step(self, form: SampleSubmissionLayoutWorkflowStep) -> SampleSubmissionLayoutWorkflowStep:
        self.add_step(form.__class__.__name__)
        match form.__class__:
            case wf.SelectLayoutTypeForm:
                next_form = wf.LayoutSpreadsheetForm(workflow=self, session=form.session)
            case _:
                raise exc.OpeNGSyncServerException(f"Unknown form class {form.__class__.__name__} in SampleSubmissionLayoutWorkflow.")

        self.previous_url = responses.url_for(
            f"{self.__class__.__name__}.{form.__class__.__name__}.Previous",
            seq_request_id=self.seq_request_id,
        ).include_query_params(uuid=self.uuid)
        self.add_step(next_form.__class__.__name__)
        return next_form

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(
            prefix="/sample-submission-layout/{seq_request_id}", tags=["sample-submission-layout"],
            dependencies=[Depends(require_seq_request_write)],
        )
        router.add_api_route("/begin", SampleSubmissionLayoutWorkflow.Begin(), methods=["GET"], name="SampleSubmissionLayoutWorkflow.Begin")
        router.include_router(wf.SelectLayoutTypeForm.Router(cls.__name__))
        router.include_router(wf.LayoutSpreadsheetForm.Router(cls.__name__))
        return router
