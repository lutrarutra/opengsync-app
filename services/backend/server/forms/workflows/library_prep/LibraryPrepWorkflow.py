from fastapi import Query, Depends, APIRouter

from opengsync_db import models, queries as Q, SyncSession, categories as C
from opengsync_db.categories import LibraryStatus, LibraryType, LabChecklistType

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
from ...common import SelectSamplesForm


class LibraryPrepWorkflow(HTMXWorkflow):
    def __init__(self, step: str, lab_prep_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.lab_prep_id = lab_prep_id

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: "LibraryPrepWorkflow" = Depends(LibraryPrepWorkflow.Init(step)),
        ) -> "LibraryPrepWorkflow":
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
        ) -> "LibraryPrepWorkflow":
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

            args: dict = dict(
                workflow="library_prep",
                select_libraries=True,
                library_status_filter=[LibraryStatus.ACCEPTED],
                select_all_libraries=True,
            )

            if lab_prep.checklist_type == LabChecklistType.CUSTOM:
                args["library_type_filter"] = None
            else:
                args["library_type_filter"] = LibraryType.get_check_list_library_types(lab_prep.checklist_type) or None

            form = SelectSamplesForm(**args, context={"lab_prep": lab_prep})
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/library-prep/{lab_prep_id}", tags=["library-prep"], dependencies=[Depends(dependencies.require_insider)])
        router.add_api_route("/begin", LibraryPrepWorkflow.Begin(), methods=["GET"], name="LibraryPrepWorkflow.begin")
        return router

    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        raise NotImplementedError()