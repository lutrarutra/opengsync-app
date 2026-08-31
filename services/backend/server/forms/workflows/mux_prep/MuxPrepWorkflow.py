from typing import Self

from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, FormFunc
from .. import mux_prep as wf


class MuxPrepWorkflowStep(HTMXWorkflowStep):
    workflow: "MuxPrepWorkflow"

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="MuxPrepWorkflow",
        ).include_query_params(uuid=self.workflow.uuid, **self.workflow._query_params)

    @classmethod
    def Init(cls: type[Self]) -> FormFunc:
        def dependency(
            workflow: MuxPrepWorkflow = Depends(MuxPrepWorkflow.Init(cls.__name__)),
        ) -> Self:
            return cls(workflow=workflow)
        return dependency

    @classmethod
    def Validate(cls: type[Self]) -> FormFunc:
        def dependency(
            form: Self = Depends(super(MuxPrepWorkflowStep, cls).Validate()),
        ) -> Self:
            return form
        return dependency


class MuxPrepWorkflow(HTMXWorkflow):
    def __init__(
        self,
        step: str,
        lab_prep_id: int,
        mux_type_id: int,
        r: redis.RedisClient,
        uuid: str | None = None,
    ) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.lab_prep_id = lab_prep_id
        self.mux_type_id = mux_type_id
        self._query_params: dict = {
            "lab_prep_id": lab_prep_id,
            "mux_type_id": mux_type_id,
        }

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            lab_prep_id: int = Query(..., description="Lab Prep ID"),
            mux_type_id: int = Query(..., description="MUX type ID"),
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            current_user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "MuxPrepWorkflow":
            if session.first(Q.lab_prep.select(id=lab_prep_id)) is None:
                raise exc.NotFoundException("Lab prep not found.")
            if C.MUXType.get(mux_type_id) is None:
                raise exc.BadRequestException("Invalid multiplexing type.")
            if not current_user.is_insider:
                raise exc.NoPermissionsException()
            return cls(
                step=step,
                lab_prep_id=lab_prep_id,
                mux_type_id=mux_type_id,
                r=r,
                uuid=uuid,
            )
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            workflow: MuxPrepWorkflow = Depends(MuxPrepWorkflow.Init("Begin")),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            mux_type = C.MUXType.get(workflow.mux_type_id)
            match mux_type:
                case C.MUXType.TENX_OLIGO:
                    form = wf.OligoMuxForm.build(workflow, session)
                case C.MUXType.TENX_FLEX_PROBE:
                    form = wf.FlexMuxForm.build(workflow, session)
                case C.MUXType.TENX_ON_CHIP:
                    form = wf.OCMMuxForm.build(workflow, session)
                case _:
                    raise exc.BadRequestException(f"Multiplexing type {mux_type} is not implemented.")
            return form.make_response()
        return route

    def get_next_step(self, form: "MuxPrepWorkflowStep") -> "MuxPrepWorkflowStep":
        self.add_step(form.__class__.__name__)
        match form.__class__:
            case wf.FlexMuxForm:
                next_form = wf.FlexABCForm.build(self)
            case _:
                raise exc.OpeNGSyncServerException(
                    f"Unknown form class {form.__class__.__name__} in MuxPrepWorkflow."
                )

        self.previous_url = responses.url_for(
            f"{self.__class__.__name__}.{form.__class__.__name__}.Previous",
        ).include_query_params(uuid=self.uuid, **self._query_params)
        self.add_step(next_form.__class__.__name__)
        return next_form

    def complete_to_lab_prep(self, message: str = "Changes saved!"):
        next_url = responses.url_for("lab_prep_page", lab_prep_id=self.lab_prep_id)
        self.complete()
        return responses.htmx_response(
            redirect=next_url,
            flash=responses.flash(message, "success"),
        )

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(
            prefix="/mux-prep",
            tags=["mux-prep"],
            dependencies=[Depends(dependencies.require_insider)],
        )
        router.add_api_route("/begin", MuxPrepWorkflow.Begin(), methods=["GET"], name="MuxPrepWorkflow.Begin")
        router.include_router(wf.OligoMuxForm.Router(cls.__name__))
        router.include_router(wf.FlexMuxForm.Router(cls.__name__))
        router.include_router(wf.FlexABCForm.Router(cls.__name__))
        router.include_router(wf.OCMMuxForm.Router(cls.__name__))
        return router
