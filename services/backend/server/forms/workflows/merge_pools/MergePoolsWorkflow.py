from typing import Self

from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, FormFunc
from .. import merge_pools as wf


class MergePoolsWorkflowStep(HTMXWorkflowStep):
    workflow: "MergePoolsWorkflow"

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="MergePoolsWorkflow",
        ).include_query_params(uuid=self.workflow.uuid, **self.workflow._query_params)

    @classmethod
    def Init(cls: type[Self]) -> FormFunc:
        def dependency(
            workflow: MergePoolsWorkflow = Depends(MergePoolsWorkflow.Init(cls.__name__)),
        ) -> Self:
            return cls(workflow=workflow)
        return dependency

    @classmethod
    def Validate(cls: type[Self]) -> FormFunc:
        def dependency(
            form: Self = Depends(super(MergePoolsWorkflowStep, cls).Validate()),
        ) -> Self:
            return form
        return dependency


class MergePoolsWorkflow(HTMXWorkflow):
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
            seq_request_id: int | None = Query(None, description="Seq Request ID to filter pools by"),
            lab_prep_id: int | None = Query(None, description="Lab Prep ID to filter pools by"),
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "MergePoolsWorkflow":
            if seq_request_id is not None:
                if session.first(Q.seq_request.select(id=seq_request_id)) is None:
                    raise exc.NotFoundException()
                if session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user.id)) < C.AccessLevel.WRITE:
                    raise exc.NoPermissionsException()
            if lab_prep_id is not None:
                if session.first(Q.lab_prep.select(id=lab_prep_id)) is None:
                    raise exc.NotFoundException()
                if not current_user.is_insider:
                    raise exc.NoPermissionsException()
            if seq_request_id is None and not current_user.is_insider:
                raise exc.NoPermissionsException()
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

    def get_next_step(self, form: "MergePoolsWorkflowStep") -> "MergePoolsWorkflowStep":
        self.add_step(form.__class__.__name__)
        match form.__class__:
            case wf.SelectSamplesForm:
                next_form = wf.MergePoolsForm(workflow=self)
            case _:
                raise exc.OpeNGSyncServerException(f"Unknown form class {form.__class__.__name__} in MergePoolsWorkflow.")

        self.previous_url = responses.url_for(
            f"{self.__class__.__name__}.{form.__class__.__name__}.Previous",
        ).include_query_params(uuid=self.uuid, **self._query_params)
        self.add_step(next_form.__class__.__name__)
        return next_form

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/merge-pools", tags=["merge-pools"])
        router.add_api_route("/begin", MergePoolsWorkflow.Begin(), methods=["GET"], name="MergePoolsWorkflow.Begin")
        router.include_router(wf.SelectSamplesForm.Router(cls.__name__))
        router.include_router(wf.MergePoolsForm.Router(cls.__name__))
        return router
