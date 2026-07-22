from typing import TypeVar

from fastapi import Query, Depends, APIRouter

from opengsync_db import models

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, FormFunc
from .. import qubit_measure as wf

T = TypeVar("T", bound="QubitMeasureWorkflowStep")

class QubitMeasureWorkflowStep(HTMXWorkflowStep):
    workflow: "QubitMeasureWorkflow"

    show_samples: bool = True
    show_libraries: bool = True
    show_pools: bool = True
    show_lanes: bool = True

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="QubitMeasureWorkflow",
        ).include_query_params(uuid=self.workflow.uuid, **self.workflow._query_params)

    @classmethod
    def Init(cls: type[T]) -> FormFunc:
        def dependency(
            workflow: QubitMeasureWorkflow = Depends(QubitMeasureWorkflow.Init(cls.__name__)),
        ) -> T:
            return cls(workflow=workflow)
        return dependency
    
    @classmethod
    def Validate(cls: type[T]) -> FormFunc:
        """Validate this step from the workflow state for an endpoint dependency."""
        def dependency(
            form: T = Depends(super(QubitMeasureWorkflowStep, cls).Validate()),
        ) -> T:
            return form
        return dependency


class QubitMeasureWorkflow(HTMXWorkflow):
    def __init__(self, step: str, experiment_id: int | None, lab_prep_id: int | None, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.experiment_id = experiment_id
        self.lab_prep_id = lab_prep_id
        self._query_params = {}
        if experiment_id is not None:
            self._query_params["experiment_id"] = experiment_id
        if lab_prep_id is not None:
            self._query_params["lab_prep_id"] = lab_prep_id

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            experiment_id: int | None = Query(None, description="Experiment ID to filter samples by"),
            lab_prep_id: int | None = Query(None, description="Lab Prep ID to filter samples by"),
            r: redis.RedisClient = Depends(dependencies.redis),
            uuid: str | None = Query(None, description="The UUID of the workflow instance"),
        ) -> "QubitMeasureWorkflow":
            return cls(step=step, experiment_id=experiment_id, lab_prep_id=lab_prep_id, r=r, uuid=uuid)
        return dependency
    

    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            form: wf.SelectSamplesForm = Depends(wf.SelectSamplesForm.Init()),
            current_user: models.User = Depends(dependencies.require_user),
        ):
            if form.workflow.lab_prep_id is not None:
                if not current_user.is_insider:
                    raise exc.NoPermissionsException("You do not have permission to access this lab prep.")
            elif form.workflow.experiment_id is not None:
                if not current_user.is_insider:
                    raise exc.NoPermissionsException("You do not have permission to access this experiment.")
            return form.make_response()
        return route
            

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/qubit-measure", tags=["qubit-measure"])
        router.add_api_route("/begin", QubitMeasureWorkflow.Begin(), methods=["GET"], name="QubitMeasureWorkflow.Begin")
        router.include_router(wf.SelectSamplesForm.Router(cls.__name__))
        router.include_router(wf.QubitMeasureForm.Router(cls.__name__))
        return router

    def get_next_step(self, form: "QubitMeasureWorkflowStep") -> "QubitMeasureWorkflowStep":
        self.add_step(form.__class__.__name__)
        match form.__class__:
            case wf.SelectSamplesForm:
                next_form = wf.QubitMeasureForm(workflow=self)
            case _:
                raise exc.OpeNGSyncServerException(f"Unknown form class {form.__class__.__name__} in QubitMeasureWorkflow.")
        
        self.previous_url = responses.url_for(f"{self.__class__.__name__}.{form.__class__.__name__}.Previous").include_query_params(uuid=self.uuid, **self._query_params)
        self.add_step(next_form.__class__.__name__)
        return next_form

