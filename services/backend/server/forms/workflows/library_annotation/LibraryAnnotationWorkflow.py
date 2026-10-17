import time
import datetime as dt
from typing import Self, Sequence

from fastapi import Query, Depends, APIRouter, Request, Response

from opengsync_db import categories as C, models, queries as Q, SyncSession

from ....core import dependencies, exceptions as exc, redis, responses
from ....components.tables import DBObjectColumn
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc, WorkflowRun, StepMode
from ...HTMXForm import RouteFunc, FormFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from .. import library_annotation as wf


class LibraryAnnotationWorkflowStep(HTMXWorkflowStep):
    """Base workflow step with standard Library Annotation construction."""

    workflow: "LibraryAnnotationWorkflow"

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="LibraryAnnotationWorkflow",
            seq_request_id=self.workflow.seq_request_id,
        ).include_query_params(uuid=self.workflow.uuid)

    @classmethod
    def Init(cls: type[Self]) -> FormFunc:
        """Create this step from the workflow state for an endpoint dependency."""
        def dependency(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__))
        ) -> Self:
            return cls(workflow=workflow)
        return dependency

    @classmethod
    def Validate(cls: type[Self]) -> FormFunc:
        """Validate this step from the workflow state for an endpoint dependency."""
        def dependency(
            form: Self = Depends(super(LibraryAnnotationWorkflowStep, cls).Validate()),
        ) -> Self:
            return form
        return dependency

    def set_sample_options(self, column: DBObjectColumn, names: Sequence[str]) -> dict[str, int]:
        """Offer the samples (or pools) ``names`` in ``column``: existing samples as "name [id]", the others as
        "name [new]". Returns the ids of the existing samples by name."""
        sample_table = self.workflow.tables["sample_table"]
        existing = sample_table.dropna(subset=["sample_id"])
        sample_ids: dict[str, int] = {
            name: int(sample_id) for name, sample_id in zip(existing["sample_name"], existing["sample_id"])
            if name in names
        }
        column.set_categories(
            {sample_id: f"{name} [{sample_id}]" for name, sample_id in sample_ids.items()},
            new_names=[name for name in names if name not in sample_ids],
        )
        return sample_ids

    def make_response(self, status_code: int = 200, **kwargs) -> Response:
        # Showing a step is activity on the run; a fresh render (not a re-render with
        # validation errors) is also where the run resumes.
        if (user_id := self.workflow.user_id) is not None:
            if self.validated:
                self.workflow.touch(user_id)
            else:
                self.workflow.touch(user_id, step=self.__class__.__name__, step_mode=self.workflow.step_mode)
        return super().make_response(status_code=status_code, **kwargs)

def require_seq_request_write(
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
) -> C.AccessLevel:
    """Every step of the workflow modifies the request, so all of them need WRITE (legacy checked this per route)."""
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException("You do not have permission to edit this sequencing request.")
    return access_level


class LibraryAnnotationWorkflow(HTMXWorkflow):
    # Someone else showing a step this recently may still be working on the run.
    ACTIVE_ELSEWHERE_SECONDS = 15 * 60

    STEP_LABELS = {
        "ProjectSelectForm": "Select Project",
        "SampleAnnotationForm": "Sample Annotation",
        "SampleAttributeAnnotationForm": "Sample Attributes",
        "SelectServiceForm": "Select Services",
        "DefineMultiplexedSamplesForm": "Define Multiplexed Samples",
        "CustomAssayAnnotationForm": "Specify Libraries",
        "PooledLibraryAnnotationForm": "Specify Library Pooling",
        "PoolMappingForm": "Specify Pools",
        "BarcodeInputForm": "Specify Barcodes",
        "TENXATACBarcodeInputForm": "Specify 10X ATAC Barcodes",
        "BarcodeMatchForm": "Match Barcodes",
        "FeatureAnnotationForm": "Feature Reference",
        "OCMAnnotationForm": "On-Chip Multiplexing",
        "OligoMuxAnnotationForm": "Oligo-Multiplexing",
        "FlexAnnotationForm": "Flex Multiplexing",
        "ParseMuxAnnotationForm": "Parse Multiplexing",
        "ParseCRISPRGuideAnnotationForm": "Parse CRISPR Guides",
        "OpenSTAnnotationForm": "OpenST Annotation",
        "VisiumAnnotationForm": "10X Visium Annotation",
        "CompleteSASForm": "Complete Submission",
    }

    def __init__(self, step: str, seq_request_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.seq_request_id = seq_request_id
        # Set per request by ``Init``: who is working on the run and how the step was reached.
        self.user_id: int | None = None
        self.step_mode: StepMode | None = None

    @staticmethod
    def context_for(seq_request_id: int) -> str:
        return f"seq_request:{seq_request_id}"

    @property
    def context(self) -> str:
        return self.context_for(self.seq_request_id)

    @staticmethod
    def may_access_run(run: WorkflowRun, user_id: int, access_level: C.AccessLevel) -> bool:
        """Insiders may see and continue every run of a request, others only the runs they started."""
        return access_level >= C.AccessLevel.INSIDER or run.started_by_id == user_id

    def authorize(self, step: str, user_id: int, access_level: C.AccessLevel) -> None:
        # The state is keyed by UUID only, so a run must be bound to the request it was
        # started for: WRITE on the request in the URL says nothing about the run's data.
        # Project selection starts (binds) a run; every other step needs a bound run.
        bound_seq_request_id = self.header.get("seq_request_id")
        if bound_seq_request_id is None and step != "ProjectSelectForm":
            raise exc.BadRequestException("This annotation has expired. Please start again.")
        if bound_seq_request_id is not None and bound_seq_request_id != self.seq_request_id:
            raise exc.BadRequestException("This annotation belongs to another sequencing request.")
        # Every step has its own URL; only steps this run has been routed to (the tracker
        # holds every reached step, incl. the one currently shown) may be shown or posted.
        if step != "ProjectSelectForm" and step not in self.step_tracker.steps:
            raise exc.BadRequestException("This step is not part of the current annotation.")
        # Runs started before the registry existed have no record and stay open to the request.
        if (run := self.run) is not None and not self.may_access_run(run, user_id, access_level):
            raise exc.NoPermissionsException("This annotation was started by another user.")

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            request: Request,
            seq_request_id: int,
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
            user_id: int = Depends(dependencies.require_user_id),
            access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
        ) -> "LibraryAnnotationWorkflow":
            workflow = cls(uuid=uuid, r=r, seq_request_id=seq_request_id, step=step)
            workflow.authorize(step, user_id, access_level)
            workflow.user_id = user_id
            # A step's GET route is its 'Previous' (Back); POSTs submit and render the next step.
            workflow.step_mode = "back" if request.method == "GET" else "forward"
            return workflow
        return dependency

    # ── Unfinished runs ────────────────────────────────────────────────

    @classmethod
    def visible_runs(cls, r: redis.RedisClient, seq_request_id: int, user_id: int, access_level: C.AccessLevel) -> list[WorkflowRun]:
        """Unfinished runs of the request the user may continue, most recently started first."""
        runs = [
            run for run in cls.unfinished_runs(r, cls.context_for(seq_request_id))
            if cls.may_access_run(run, user_id, access_level)
        ]
        return sorted(runs, key=lambda run: run.started_at, reverse=True)

    @classmethod
    def unfinished_runs_response(
        cls, session: SyncSession, runs: list[WorkflowRun], seq_request_id: int, user_id: int,
        flash: responses.FlashMessage | None = None,
    ) -> Response:
        users = {
            uid: session.first(Q.user.select(id=uid))
            for uid in {run.started_by_id for run in runs} | {run.last_active_by_id for run in runs}
        }
        now = time.time()
        rows = []
        for run in runs:
            if run.step_mode == "back":
                # Reached via 'Back': its 'Previous' route prefills what it was submitted with
                continue_url = responses.url_for(f"{cls.__name__}.{run.step}.Previous", seq_request_id=seq_request_id)
            else:
                continue_url = responses.url_for(f"{cls.__name__}.Resume", seq_request_id=seq_request_id)
            idle_seconds = now - run.last_active_at
            rows.append({
                "run": run,
                "started_by": users.get(run.started_by_id),
                "last_active_by": users.get(run.last_active_by_id),
                "started_at": dt.datetime.fromtimestamp(run.started_at, tz=dt.timezone.utc),
                "last_active_at": dt.datetime.fromtimestamp(run.last_active_at, tz=dt.timezone.utc),
                "is_own": run.started_by_id == user_id,
                "active_elsewhere_minutes": (
                    int(idle_seconds // 60)
                    if run.last_active_by_id != user_id and idle_seconds < cls.ACTIVE_ELSEWHERE_SECONDS
                    else None
                ),
                "step_label": cls.STEP_LABELS.get(run.step, run.step),
                "continue_url": continue_url.include_query_params(uuid=run.uuid),
                "discard_url": responses.url_for(f"{cls.__name__}.Discard", seq_request_id=seq_request_id, run_uuid=run.uuid),
            })
        return responses.htmx_response(
            template="workflows/library_annotation/sas-unfinished_runs.html",
            rows=rows,
            new_url=responses.url_for(f"{cls.__name__}.Begin", seq_request_id=seq_request_id).include_query_params(new=True),
            flash=flash,
        )

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            seq_request_id: int,
            new: bool = Query(False, description="Start a new annotation without listing the unfinished ones."),
            access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
            r: redis.RedisClient = Depends(dependencies.redis),
            form: wf.ProjectSelectForm = Depends(wf.ProjectSelectForm.Init()),
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to begin this workflow.")

            if not new and (runs := cls.visible_runs(r, seq_request_id, current_user.id, access_level)):
                return cls.unfinished_runs_response(session, runs, seq_request_id, current_user.id)
            return form.make_response()
        return route

    @classmethod
    def Resume(cls) -> RouteFunc:
        """Show the step a run was left at, as it was rendered after submitting the step before it."""
        def route(
            seq_request_id: int,
            uuid: str = Query(..., description="The UUID of the workflow state."),
            access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
            current_user: models.User = Depends(dependencies.require_user),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> Response:
            if (run := cls.load_run(r, uuid)) is None:
                raise exc.BadRequestException("This annotation has expired. Please start again.")
            workflow = cls(step=run.step, seq_request_id=seq_request_id, r=r, uuid=uuid)
            workflow.authorize(run.step, current_user.id, access_level)
            workflow.user_id = current_user.id
            if run.step == "ProjectSelectForm" or (step_cls := getattr(wf, run.step, None)) is None:
                raise exc.BadRequestException("This annotation cannot be resumed. Please start again.")
            return step_cls(workflow).make_response()
        return route

    @classmethod
    def Discard(cls) -> RouteFunc:
        def route(
            seq_request_id: int,
            run_uuid: str,
            access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
            r: redis.RedisClient = Depends(dependencies.redis),
            form: wf.ProjectSelectForm = Depends(wf.ProjectSelectForm.Init()),
        ) -> Response:
            run = cls.load_run(r, run_uuid)
            if run is None or run.context != cls.context_for(seq_request_id):
                raise exc.BadRequestException("This annotation has already been completed, discarded, or has expired.")
            if not cls.may_access_run(run, current_user.id, access_level):
                raise exc.NoPermissionsException("This annotation was started by another user.")
            cls(step=run.step, seq_request_id=seq_request_id, r=r, uuid=run_uuid).complete()

            flash = responses.flash("Annotation discarded.", "success")
            if runs := cls.visible_runs(r, seq_request_id, current_user.id, access_level):
                return cls.unfinished_runs_response(session, runs, seq_request_id, current_user.id, flash=flash)
            return form.make_response(flash=flash)
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/library-annotation/{seq_request_id}", tags=["library-annotation"], dependencies=[Depends(require_seq_request_write)])
        router.add_api_route("/begin", LibraryAnnotationWorkflow.Begin(), methods=["GET"], name="LibraryAnnotationWorkflow.Begin")
        router.add_api_route("/resume", LibraryAnnotationWorkflow.Resume(), methods=["GET"], name="LibraryAnnotationWorkflow.Resume")
        router.add_api_route("/unfinished/{run_uuid}", LibraryAnnotationWorkflow.Discard(), methods=["DELETE"], name="LibraryAnnotationWorkflow.Discard")
        router.include_router(wf.ProjectSelectForm.Router(cls.__name__))
        router.include_router(wf.SampleAnnotationForm.Router(cls.__name__))
        router.include_router(wf.SampleAttributeAnnotationForm.Router(cls.__name__))
        router.include_router(wf.SelectServiceForm.Router(cls.__name__))
        router.include_router(wf.PoolMappingForm.Router(cls.__name__))
        router.include_router(wf.PooledLibraryAnnotationForm.Router(cls.__name__))
        router.include_router(wf.FeatureAnnotationForm.Router(cls.__name__))
        router.include_router(wf.OpenSTAnnotationForm.Router(cls.__name__))
        router.include_router(wf.VisiumAnnotationForm.Router(cls.__name__))
        router.include_router(wf.ParseCRISPRGuideAnnotationForm.Router(cls.__name__))
        router.include_router(wf.CustomAssayAnnotationForm.Router(cls.__name__))
        router.include_router(wf.OCMAnnotationForm.Router(cls.__name__))
        router.include_router(wf.OligoMuxAnnotationForm.Router(cls.__name__))
        router.include_router(wf.FlexAnnotationForm.Router(cls.__name__))
        router.include_router(wf.ParseMuxAnnotationForm.Router(cls.__name__))
        router.include_router(wf.DefineMultiplexedSamplesForm.Router(cls.__name__))
        router.include_router(wf.BarcodeInputForm.Router(cls.__name__))
        router.include_router(wf.TENXATACBarcodeInputForm.Router(cls.__name__))
        router.include_router(wf.BarcodeMatchForm.Router(cls.__name__))
        router.include_router(wf.CompleteSASForm.Router(cls.__name__))
        return router
    
    def get_next_step(self, form: "LibraryAnnotationWorkflowStep") -> "LibraryAnnotationWorkflowStep":
        self.add_step(form.__class__.__name__)
        match form.__class__:
            case wf.ProjectSelectForm:
                next_form = wf.SampleAnnotationForm(self)
            case wf.SampleAnnotationForm:
                next_form = wf.SampleAttributeAnnotationForm(self)
            case wf.SampleAttributeAnnotationForm:
                next_form = wf.SelectServiceForm(self)
            case wf.SelectServiceForm:
                if wf.PooledLibraryAnnotationForm.is_applicable(self):
                    next_form = wf.PooledLibraryAnnotationForm(self)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    next_form = wf.FeatureAnnotationForm(self)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    next_form = wf.OpenSTAnnotationForm(self)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    next_form = wf.VisiumAnnotationForm(self)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case wf.CustomAssayAnnotationForm:
                if wf.OCMAnnotationForm.is_applicable(self):
                    next_form = wf.OCMAnnotationForm(self)
                elif wf.OligoMuxAnnotationForm.is_applicable(self):
                    next_form = wf.OligoMuxAnnotationForm(self)
                elif wf.FlexAnnotationForm.is_applicable(self):
                    next_form = wf.FlexAnnotationForm(self)
                elif wf.ParseMuxAnnotationForm.is_applicable(self):
                    next_form = wf.ParseMuxAnnotationForm(self)
                elif wf.PooledLibraryAnnotationForm.is_applicable(self):
                    next_form = wf.PooledLibraryAnnotationForm(self)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    next_form = wf.FeatureAnnotationForm(self)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    next_form = wf.OpenSTAnnotationForm(self)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    next_form = wf.VisiumAnnotationForm(self)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case wf.DefineMultiplexedSamplesForm:
                if wf.OligoMuxAnnotationForm.is_applicable(self):
                    next_form = wf.OligoMuxAnnotationForm(self)
                elif wf.OCMAnnotationForm.is_applicable(self):
                    next_form = wf.OCMAnnotationForm(self)
                elif wf.FlexAnnotationForm.is_applicable(self):
                    next_form = wf.FlexAnnotationForm(self)
                elif wf.ParseMuxAnnotationForm.is_applicable(self):
                    next_form = wf.ParseMuxAnnotationForm(self)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    next_form = wf.FeatureAnnotationForm(self)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    next_form = wf.OpenSTAnnotationForm(self)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    next_form = wf.VisiumAnnotationForm(self)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case wf.PooledLibraryAnnotationForm:
                next_form = wf.PoolMappingForm(self)
            case wf.PoolMappingForm:
                if wf.BarcodeInputForm.is_applicable(self):
                    next_form = wf.BarcodeInputForm(self,)
                elif wf.TENXATACBarcodeInputForm.is_applicable(self):
                    next_form = wf.TENXATACBarcodeInputForm(self)
                else:
                    raise exc.OpeNGSyncServerException("No applicable next step found after PoolMappingForm.")
            case wf.BarcodeInputForm:
                # ATAC indices are entered before matching, so BarcodeMatch runs once for all inputs
                if wf.TENXATACBarcodeInputForm.is_applicable(self):
                    next_form = wf.TENXATACBarcodeInputForm(self)
                elif wf.BarcodeMatchForm.is_applicable(self):
                    next_form = wf.BarcodeMatchForm(self)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    next_form = wf.FeatureAnnotationForm(self)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    next_form = wf.OpenSTAnnotationForm(self)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    next_form = wf.VisiumAnnotationForm(self)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case wf.TENXATACBarcodeInputForm:
                if wf.BarcodeMatchForm.is_applicable(self):
                    next_form = wf.BarcodeMatchForm(self)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    next_form = wf.FeatureAnnotationForm(self)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    next_form = wf.OpenSTAnnotationForm(self)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    next_form = wf.VisiumAnnotationForm(self)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case wf.FeatureAnnotationForm:
                if wf.OpenSTAnnotationForm.is_applicable(self):
                    next_form = wf.OpenSTAnnotationForm(self)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    next_form = wf.VisiumAnnotationForm(self)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case wf.VisiumAnnotationForm:
                if wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case wf.ParseCRISPRGuideAnnotationForm:
                next_form = wf.CompleteSASForm(self)
            case wf.OpenSTAnnotationForm:
                if wf.VisiumAnnotationForm.is_applicable(self):
                    next_form = wf.VisiumAnnotationForm(self)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case wf.BarcodeMatchForm:
                if wf.FeatureAnnotationForm.is_applicable(self):
                    next_form = wf.FeatureAnnotationForm(self)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    next_form = wf.OpenSTAnnotationForm(self)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    next_form = wf.VisiumAnnotationForm(self)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case wf.FlexAnnotationForm:
                if self.submission_type == C.SubmissionType.POOLED_LIBRARIES:
                    next_form = wf.PooledLibraryAnnotationForm(self)
                elif wf.ParseMuxAnnotationForm.is_applicable(self):
                    next_form = wf.ParseMuxAnnotationForm(self)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    next_form = wf.FeatureAnnotationForm(self)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    next_form = wf.OpenSTAnnotationForm(self)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    next_form = wf.VisiumAnnotationForm(self)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case wf.OCMAnnotationForm:
                if wf.FlexAnnotationForm.is_applicable(self):
                    next_form = wf.FlexAnnotationForm(self)
                elif wf.ParseMuxAnnotationForm.is_applicable(self):
                    next_form = wf.ParseMuxAnnotationForm(self)
                elif self.submission_type == C.SubmissionType.POOLED_LIBRARIES:
                    next_form = wf.PooledLibraryAnnotationForm(self)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    next_form = wf.FeatureAnnotationForm(self)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    next_form = wf.OpenSTAnnotationForm(self)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    next_form = wf.VisiumAnnotationForm(self)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case wf.OligoMuxAnnotationForm:
                if self.submission_type == C.SubmissionType.POOLED_LIBRARIES:
                    next_form = wf.PooledLibraryAnnotationForm(self)
                elif wf.OCMAnnotationForm.is_applicable(self):
                    next_form = wf.OCMAnnotationForm(self)
                elif wf.FlexAnnotationForm.is_applicable(self):
                    next_form = wf.FlexAnnotationForm(self)
                elif wf.ParseMuxAnnotationForm.is_applicable(self):
                    next_form = wf.ParseMuxAnnotationForm(self)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    next_form = wf.FeatureAnnotationForm(self)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    next_form = wf.OpenSTAnnotationForm(self)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    next_form = wf.VisiumAnnotationForm(self)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case wf.ParseMuxAnnotationForm:
                if self.submission_type == C.SubmissionType.POOLED_LIBRARIES:
                    next_form = wf.PooledLibraryAnnotationForm(self)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    next_form = wf.FeatureAnnotationForm(self)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    next_form = wf.OpenSTAnnotationForm(self)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    next_form = wf.VisiumAnnotationForm(self)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    next_form = wf.ParseCRISPRGuideAnnotationForm(self)
                else:
                    next_form = wf.CompleteSASForm(self)
            case _:
                raise ValueError(f"Unknown form type: {form.__class__.__name__}")

        self._link_previous(form, next_form)
        return next_form

    def advance_to(self, form: "LibraryAnnotationWorkflowStep", next_form_cls: type["LibraryAnnotationWorkflowStep"]) -> "LibraryAnnotationWorkflowStep":
        """Route ``form`` to a fixed next step, with the same bookkeeping as ``get_next_step``."""
        self.add_step(form.__class__.__name__)
        next_form = next_form_cls(self)
        self._link_previous(form, next_form)
        return next_form

    def _link_previous(self, form: "LibraryAnnotationWorkflowStep", next_form: "LibraryAnnotationWorkflowStep") -> None:
        # Store the back URL on the destination step.  This preserves the
        # current step's own back URL when navigating forward after returning
        # from a later step.
        self.previous_url = responses.url_for(
            f"{self.__class__.__name__}.{form.__class__.__name__}.Previous",
            seq_request_id=self.seq_request_id,
        ).include_query_params(uuid=self.uuid)
        self.add_step(next_form.__class__.__name__)

    def existing_libraries(self, session: SyncSession) -> set[tuple[str, int]]:
        """(sample name, library type id) of every library already linked to a sample of this request."""
        df = session.get_pandas(Q.pd.seq_request_samples(self.seq_request_id), limit=None)
        return {(row["sample_name"], C.LibraryType.get(row["library_type"]).id) for _, row in df.iterrows()}

    def add_comment(self, context: str, text: str) -> None:
        # One comment per context (as in legacy), so re-submitting a step after 'Back' replaces it
        comments = [c for c in self.metadata.get("comments", []) if c["context"] != context]
        comments.append({"context": context, "comment": text})
        self.metadata["comments"] = comments

    def get_comments(self) -> list[dict[str, str]]:
        return self.metadata.get("comments", [])

    @property
    def submission_type(self) -> C.SubmissionType:
        return C.SubmissionType.get(self.header["submission_type_id"])