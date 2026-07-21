from typing import TypeVar

from fastapi import Query, Depends, APIRouter

from opengsync_db import categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ...HTMXForm import RouteFunc, FormFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from .. import library_annotation as wf


T = TypeVar("T", bound="LibraryAnnotationWorkflowStep")


class LibraryAnnotationWorkflowStep(HTMXWorkflowStep):
    """Base workflow step with standard Library Annotation construction."""

    workflow: LibraryAnnotationWorkflow

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="LibraryAnnotationWorkflow",
            seq_request_id=self.workflow.seq_request_id,
        ).include_query_params(uuid=self.workflow.uuid)

    @classmethod
    def Init(cls: type[T]) -> FormFunc:
        """Create this step from the workflow state for an endpoint dependency."""
        def dependency(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__))
        ) -> T:
            return cls(workflow=workflow)
        return dependency

    @classmethod
    def Validate(cls: type[T]) -> FormFunc:
        """Validate this step from the workflow state for an endpoint dependency."""
        def dependency(
            form: T = Depends(super(LibraryAnnotationWorkflowStep, cls).Validate()),
        ) -> T:
            return form
        return dependency

class LibraryAnnotationWorkflow(HTMXWorkflow):    
    def __init__(self, step: str, seq_request_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.seq_request_id = seq_request_id

    @classmethod
    def Init(cls, step: str) -> WorkflowFunc:
        def dependency(
            seq_request_id: int,
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "LibraryAnnotationWorkflow":
            return cls(uuid=uuid, r=r, seq_request_id=seq_request_id, step=step)
        return dependency
    
    @classmethod
    def Begin(cls) -> RouteFunc:
        def route(
            access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
            form: wf.ProjectSelectForm = Depends(wf.ProjectSelectForm.Init()),
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.OpeNGSyncServerException("You do not have permission to begin this workflow.")
            
            return form.make_response()
        return route

    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/library-annotation/{seq_request_id}", tags=["library-annotation"], dependencies=[Depends(dependencies.seq_request_permissions)])
        router.add_api_route("/begin", LibraryAnnotationWorkflow.Begin(), methods=["GET"], name="LibraryAnnotationWorkflow.Begin")
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
                if wf.BarcodeMatchForm.is_applicable(self):
                    next_form = wf.BarcodeMatchForm(self)
                elif wf.TENXATACBarcodeInputForm.is_applicable(self):
                    next_form = wf.TENXATACBarcodeInputForm(self)
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

        self.previous_url = responses.url_for(f"{self.__class__.__name__}.{form.__class__.__name__}.Previous", seq_request_id=self.seq_request_id).include_query_params(uuid=self.uuid)
        self.add_step(next_form.__class__.__name__)
        return next_form

    def add_comment(self, context: str, text: str) -> None:
        if "comments" not in self.metadata:
            self.metadata["comments"] = []
        self.metadata["comments"].append({"context": context, "comment": text})

    def get_comments(self) -> list[dict[str, str]]:
        return self.metadata.get("comments", [])

    @property
    def submission_type(self) -> C.SubmissionType:
        return C.SubmissionType.get(self.header["submission_type_id"])