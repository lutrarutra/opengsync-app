from typing import Self

from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, FormFunc
from .. import reindex as wf


class ReindexWorkflowStep(HTMXWorkflowStep):
    workflow: "ReindexWorkflow"

    def __init__(self, workflow: "ReindexWorkflow") -> None:
        super().__init__(workflow=workflow)
        self.post_url = responses.url_for(f"{self.workflow.__class__.__name__}.{self.__class__.__name__}.Submit").include_query_params(uuid=self.workflow.uuid, **self.workflow._query_params)

    @classmethod
    def Init(cls: type[Self]) -> FormFunc:
        def dependency(
            workflow: ReindexWorkflow = Depends(ReindexWorkflow.Init(cls.__name__))
        ) -> Self:
            return cls(workflow=workflow)
        return dependency

    @classmethod
    def Validate(cls: type[Self]) -> FormFunc:
        def dependency(
            form: Self = Depends(super(ReindexWorkflowStep, cls).Validate()),
        ) -> Self:
            return form
        return dependency


class ReindexWorkflow(HTMXWorkflow):
    def __init__(self, step: str, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.seq_request_id: int | None = None
        self.lab_prep_id: int | None = None
        self.pool_id: int | None = None
        self._query_params: dict = {}

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            seq_request_id: int | None = Query(None, description="Seq Request ID to filter libraries by"),
            lab_prep_id: int | None = Query(None, description="Lab Prep ID to filter libraries by"),
            pool_id: int | None = Query(None, description="Pool ID to filter libraries by"),
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "ReindexWorkflow":
            workflow = cls(uuid=uuid, r=r, step=step)
            workflow.seq_request_id = seq_request_id
            workflow.lab_prep_id = lab_prep_id
            workflow.pool_id = pool_id
            workflow._query_params = {}
            if seq_request_id is not None:
                if session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user.id)) < C.AccessLevel.WRITE:
                    raise exc.NoPermissionsException("You do not have permission to edit this seq request.")
                workflow._query_params["seq_request_id"] = seq_request_id
            if lab_prep_id is not None:
                if not current_user.is_insider:
                    raise exc.NoPermissionsException("You do not have permission to access this lab prep.")
                workflow._query_params["lab_prep_id"] = lab_prep_id
            if pool_id is not None:
                if session.get_access_level(Q.pool.permissions(pool_id, current_user.id)) < C.AccessLevel.WRITE:
                    raise exc.NoPermissionsException("You do not have permission to edit this pool.")
                workflow._query_params["pool_id"] = pool_id
            return workflow
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            form: wf.SelectSamplesForm = Depends(wf.SelectSamplesForm.Init()),
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            if form.workflow.lab_prep_id is not None:
                if not current_user.is_insider:
                    raise exc.NoPermissionsException("You do not have permission to access this lab prep.")
            elif form.workflow.pool_id is not None:
                if not current_user.is_insider:
                    raise exc.NoPermissionsException("You do not have permission to access this pool.")
            elif form.workflow.seq_request_id is not None and session.get_access_level(Q.seq_request.permissions(form.workflow.seq_request_id, current_user.id)) < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to edit this seq request.")
            return form.make_response() 
        return route

    def get_next_step(self, form: "ReindexWorkflowStep") -> "ReindexWorkflowStep":
        """Advance to the next reindex step and remember how to go back."""
        self.add_step(form.__class__.__name__)

        match form.__class__:
            case wf.SelectSamplesForm:
                if wf.BarcodeInputForm.is_applicable(form.workflow):
                    next_step_class = wf.BarcodeInputForm
                elif wf.TENXATACBarcodeInputForm.is_applicable(form.workflow):
                    next_step_class = wf.TENXATACBarcodeInputForm
                elif wf.BarcodeMatchForm.is_applicable(form.workflow):
                    next_step_class = wf.BarcodeMatchForm
                else:
                    next_step_class = wf.CompleteReindexForm
            case wf.BarcodeInputForm:
                if wf.TENXATACBarcodeInputForm.is_applicable(form.workflow):
                    next_step_class = wf.TENXATACBarcodeInputForm
                elif wf.BarcodeMatchForm.is_applicable(form.workflow):
                    next_step_class = wf.BarcodeMatchForm
                else:
                    next_step_class = wf.CompleteReindexForm
            case wf.TENXATACBarcodeInputForm:
                if wf.BarcodeMatchForm.is_applicable(form.workflow):
                    next_step_class = wf.BarcodeMatchForm
                else:
                    next_step_class = wf.CompleteReindexForm
            case wf.BarcodeMatchForm:
                next_step_class = wf.CompleteReindexForm
            case _:
                raise exc.OpeNGSyncServerException(
                    f"Unknown form class {form.__class__.__name__} in ReindexWorkflow."
                )

        next_step = next_step_class(workflow=self)
        # Store the back URL on the destination step.  Storing it before
        # constructing the destination overwrites the current step's own back
        # URL when the user navigates forward again after going back.
        self.previous_url = responses.url_for(
            f"{self.__class__.__name__}.{form.__class__.__name__}.Previous",
        ).include_query_params(uuid=self.uuid, **self._query_params)
        self.add_step(next_step.__class__.__name__)
        return next_step

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/reindex", tags=["reindex"])
        router.add_api_route("/begin", ReindexWorkflow.Begin(), methods=["GET"], name="ReindexWorkflow.Begin")
        router.include_router(wf.SelectSamplesForm.Router(cls.__name__))
        router.include_router(wf.BarcodeInputForm.Router(cls.__name__))
        router.include_router(wf.TENXATACBarcodeInputForm.Router(cls.__name__))
        router.include_router(wf.BarcodeMatchForm.Router(cls.__name__))
        router.include_router(wf.CompleteReindexForm.Router(cls.__name__))
        return router