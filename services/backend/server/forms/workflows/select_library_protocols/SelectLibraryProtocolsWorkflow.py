import os

import pandas as pd
from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, redis, responses, config
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
# from ...select_library_protocols import LibraryProtocolSelectForm, ProtocolMappingForm


class SelectLibraryProtocolsWorkflow(HTMXWorkflow):
    def __init__(self, step: str, lab_prep_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.lab_prep_id = lab_prep_id

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "SelectLibraryProtocolsWorkflow" = Depends(SelectLibraryProtocolsWorkflow.Init(step)),
        ) -> "SelectLibraryProtocolsWorkflow":
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
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "SelectLibraryProtocolsWorkflow":
            return cls(uuid=uuid, r=r, lab_prep_id=lab_prep_id, step=step)
        return dependency

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            lab_prep_id: int,
            user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            if (lab_prep := session.first(Q.lab_prep.select(id=lab_prep_id))) is None:
                raise exc.ItemNotFoundException()

            if lab_prep.prep_file is None:
                data = {
                    "library_id": [],
                    "protocol_id": [],
                }
                for library in lab_prep.libraries:
                    data["library_id"].append(library.id)
                    data["protocol_id"].append(library.protocol_id)

                library_table = pd.DataFrame(data)
                return LibraryProtocolSelectForm(lab_prep=lab_prep, uuid=None, library_table=library_table).make_response()

            if os.path.exists(path := os.path.join(config.settings.app_config.media_folder, lab_prep.prep_file.path)):
                df = pd.read_excel(path, sheet_name="prep_table")
            else:
                df = pd.DataFrame()

            if "library_kits" not in df.columns or df["library_kits"].isna().all():
                data = {
                    "library_id": [],
                    "protocol_id": [],
                }
                for library in lab_prep.libraries:
                    data["library_id"].append(library.id)
                    data["protocol_id"].append(library.protocol_id)

                library_table = pd.DataFrame(data)
                return LibraryProtocolSelectForm(lab_prep=lab_prep, uuid=None, library_table=library_table).make_response()

            return ProtocolMappingForm(lab_prep=lab_prep, uuid=None).make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/select-library-protocols/{lab_prep_id}", tags=["select-library-protocols"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", SelectLibraryProtocolsWorkflow.Begin(), methods=["GET"], name="SelectLibraryProtocolsWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()