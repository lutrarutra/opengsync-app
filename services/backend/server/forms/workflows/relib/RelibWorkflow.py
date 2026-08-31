from typing import Self

from fastapi import Query, Depends, APIRouter

from opengsync_db import queries as Q, SyncSession

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, FormFunc
from .. import relib as wf


class RelibWorkflowStep(HTMXWorkflowStep):
    workflow: "RelibWorkflow"

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="RelibWorkflow",
        ).include_query_params(uuid=self.workflow.uuid, **self.workflow._query_params)

    @classmethod
    def Init(cls: type[Self]) -> FormFunc:
        def dependency(
            workflow: RelibWorkflow = Depends(RelibWorkflow.Init(cls.__name__)),
        ) -> Self:
            return cls(workflow=workflow)
        return dependency

    @classmethod
    def Validate(cls: type[Self]) -> FormFunc:
        def dependency(
            form: Self = Depends(super(RelibWorkflowStep, cls).Validate()),
        ) -> Self:
            return form
        return dependency


class RelibWorkflow(HTMXWorkflow):
    def __init__(
        self,
        step: str,
        seq_request_id: int | None,
        lab_prep_id: int | None,
        r: redis.RedisClient,
        uuid: str | None = None,
    ) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.seq_request_id = seq_request_id
        self.lab_prep_id = lab_prep_id
        self._query_params: dict = {}
        if seq_request_id is not None:
            self._query_params["seq_request_id"] = seq_request_id
        if lab_prep_id is not None:
            self._query_params["lab_prep_id"] = lab_prep_id

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            seq_request_id: int | None = Query(None, description="Seq Request ID to filter libraries by"),
            lab_prep_id: int | None = Query(None, description="Lab Prep ID to filter libraries by"),
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            session: SyncSession = Depends(dependencies.db_session),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "RelibWorkflow":
            if seq_request_id is not None and session.first(Q.seq_request.select(id=seq_request_id)) is None:
                raise exc.NotFoundException("Seq request not found.")
            if lab_prep_id is not None and session.first(Q.lab_prep.select(id=lab_prep_id)) is None:
                raise exc.NotFoundException("Lab prep not found.")
            return cls(
                step=step,
                seq_request_id=seq_request_id,
                lab_prep_id=lab_prep_id,
                r=r,
                uuid=uuid,
            )
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            form: wf.SelectSamplesForm = Depends(wf.SelectSamplesForm.Init()),
        ):
            return form.make_response()
        return route

    def get_next_step(self, form: "RelibWorkflowStep") -> "RelibWorkflowStep":
        self.add_step(form.__class__.__name__)
        match form.__class__:
            case wf.SelectSamplesForm:
                next_form = wf.LibraryEditTableForm(workflow=self)
            case _:
                raise exc.OpeNGSyncServerException(f"Unknown form class {form.__class__.__name__} in RelibWorkflow.")

        self.previous_url = responses.url_for(
            f"{self.__class__.__name__}.{form.__class__.__name__}.Previous",
        ).include_query_params(uuid=self.uuid, **self._query_params)
        self.add_step(next_form.__class__.__name__)
        return next_form

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/relib", tags=["relib"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", RelibWorkflow.Begin(), methods=["GET"], name="RelibWorkflow.Begin")
        router.include_router(wf.SelectSamplesForm.Router(cls.__name__))
        router.include_router(wf.LibraryEditTableForm.Router(cls.__name__))
        return router
