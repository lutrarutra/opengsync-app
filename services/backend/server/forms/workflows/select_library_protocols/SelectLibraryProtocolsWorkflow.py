from typing import Self
import os

import pandas as pd
from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession

from ....core import dependencies, exceptions as exc, redis, responses, config
from ....core.context import ctx
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, FormFunc
from .. import select_library_protocols as wf


class SelectLibraryProtocolsWorkflowStep(HTMXWorkflowStep):
    workflow: "SelectLibraryProtocolsWorkflow"

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="SelectLibraryProtocolsWorkflow",
        ).include_query_params(uuid=self.workflow.uuid, **self.workflow._query_params)

    @classmethod
    def Init(cls: type[Self]) -> FormFunc:
        def dependency(
            workflow: SelectLibraryProtocolsWorkflow = Depends(SelectLibraryProtocolsWorkflow.Init(cls.__name__)),
        ) -> Self:
            return cls(workflow=workflow)
        return dependency

    @classmethod
    def Validate(cls: type[Self]) -> FormFunc:
        def dependency(
            form: Self = Depends(super(SelectLibraryProtocolsWorkflowStep, cls).Validate()),
        ) -> Self:
            return form
        return dependency


class SelectLibraryProtocolsWorkflow(HTMXWorkflow):
    def __init__(
        self,
        step: str,
        lab_prep_id: int,
        r: redis.RedisClient,
        uuid: str | None = None,
    ) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.lab_prep_id = lab_prep_id
        self._query_params: dict = {"lab_prep_id": lab_prep_id}

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            lab_prep_id: int = Query(..., description="Lab Prep ID"),
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            current_user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "SelectLibraryProtocolsWorkflow":
            if session.first(Q.lab_prep.select(id=lab_prep_id)) is None:
                raise exc.NotFoundException("Lab prep not found.")
            if not current_user.is_insider:
                raise exc.NoPermissionsException()
            return cls(step=step, lab_prep_id=lab_prep_id, r=r, uuid=uuid)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            workflow: SelectLibraryProtocolsWorkflow = Depends(SelectLibraryProtocolsWorkflow.Init("Begin")),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            lab_prep = session.get_one(Q.lab_prep.select(id=workflow.lab_prep_id))
            flash = None

            def libraries_table() -> pd.DataFrame:
                return pd.DataFrame({
                    "library_id": [library.id for library in lab_prep.libraries],
                    "protocol_id": [library.protocol_id for library in lab_prep.libraries],
                })

            if lab_prep.prep_file is None:
                form = wf.LibraryProtocolSelectForm.build(workflow, session, library_table=libraries_table())
                return form.make_response()

            path = os.path.join(config.settings.app_config.media_folder, lab_prep.prep_file.path)
            if os.path.exists(path):
                df = pd.read_excel(path, sheet_name="prep_table")
            else:
                flash = responses.flash("Library prep file not found..", "warning")
                df = pd.DataFrame()

            if "library_kits" not in df.columns or df["library_kits"].isna().all():
                form = wf.LibraryProtocolSelectForm.build(workflow, session, library_table=libraries_table())
                return form.make_response(flash=flash)

            form = wf.ProtocolMappingForm.build(workflow, session)
            return form.make_response(flash=flash)
        return route

    def get_next_step(self, form: "SelectLibraryProtocolsWorkflowStep") -> "SelectLibraryProtocolsWorkflowStep":
        self.add_step(form.__class__.__name__)
        match form.__class__:
            case wf.ProtocolMappingForm:
                next_form = wf.LibraryProtocolSelectForm.build(self, ctx.session)
            case _:
                raise exc.OpeNGSyncServerException(f"Unknown form class {form.__class__.__name__} in SelectLibraryProtocolsWorkflow.")

        self.previous_url = responses.url_for(
            f"{self.__class__.__name__}.{form.__class__.__name__}.Previous",
        ).include_query_params(uuid=self.uuid, **self._query_params)
        self.add_step(next_form.__class__.__name__)
        return next_form

    def complete_to_lab_prep(self, message: str = "Protocols Submitted!"):
        next_url = responses.url_for("lab_prep_page", lab_prep_id=self.lab_prep_id).include_query_params(
            tab="lab_prep-checklist-tab",
        )
        self.complete()
        return responses.htmx_response(redirect=next_url, flash=responses.flash(message, "success"))

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(
            prefix="/select-library-protocols",
            tags=["select-library-protocols"],
            dependencies=[Depends(dependencies.require_insider)],
        )
        router.add_api_route(
            "/begin",
            SelectLibraryProtocolsWorkflow.Begin(),
            methods=["GET"],
            name="SelectLibraryProtocolsWorkflow.Begin",
        )
        router.include_router(wf.ProtocolMappingForm.Router(cls.__name__))
        router.include_router(wf.LibraryProtocolSelectForm.Router(cls.__name__))
        return router
