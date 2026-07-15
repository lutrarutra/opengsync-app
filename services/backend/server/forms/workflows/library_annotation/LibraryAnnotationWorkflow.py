from fastapi import Query, Depends, APIRouter

from opengsync_db import categories as C

from ....core import dependencies, exceptions as exc, redis, responses
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc
from .. import library_annotation as wf

class LibraryAnnotationWorkflow(HTMXWorkflow):    
    def __init__(self, step: str, seq_request_id: int, r: redis.RedisClient, uuid: str | None = None) -> None:
        super().__init__(uuid=uuid, r=r, step=step)
        self.seq_request_id = seq_request_id

    @classmethod
    def Previous(cls, step: str) -> WorkflowFunc:
        def dependency(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(step)),
        ) -> "LibraryAnnotationWorkflow":
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

    # @property
    # def previous_url(self) -> responses.URL:
    #     return responses.url_for("LibraryAnnotationWorkflow.previous", seq_request_id=self.seq_request_id).include_query_params(uuid=self.uuid)
            
    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter(prefix="/library-annotation/{seq_request_id}", tags=["library-annotation"], dependencies=[Depends(dependencies.seq_request_permissions)])
        router.add_api_route("/begin", LibraryAnnotationWorkflow.Begin(), methods=["GET"], name="LibraryAnnotationWorkflow.begin")
        router.include_router(wf.ProjectSelectForm.Router(cls.__name__))
        router.include_router(wf.SampleAnnotationForm.Router(cls.__name__))
        router.include_router(wf.SampleAttributeAnnotationForm.Router(cls.__name__))
        router.include_router(wf.SelectServiceForm.Router(cls.__name__))
        return router
    
    def get_next_step(self, form: "HTMXWorkflowStep") -> "HTMXWorkflowStep":
        match form.__class__:
            case wf.ProjectSelectForm:
                next_form = wf.SampleAnnotationForm(workflow=self)
            case wf.SampleAnnotationForm:
                next_form = wf.SampleAttributeAnnotationForm(workflow=self)
            case wf.SampleAttributeAnnotationForm:
                next_form = wf.SelectServiceForm(workflow=self)
            case wf.SelectServiceForm:
                raise NotImplementedError()
            case _:
                raise ValueError(f"Unknown form type: {form.__class__.__name__}")

        self.previous_url = responses.url_for(f"{self.__class__.__name__}.{form.__class__.__name__}.Previous", seq_request_id=self.seq_request_id).include_query_params(uuid=self.uuid)
        self.add_step(form.__class__.__name__)
        self.add_step(next_form.__class__.__name__)
        return next_form
        # case wf.SelectServiceForm:
            #     if self.seq_request.submission_type.id == C.SubmissionType.POOLED_LIBRARIES.id:
            #         return wf.PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.FeatureAnnotationForm.is_applicable(self):
            #         return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OpenSTAnnotationForm.is_applicable(self):
            #         return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.VisiumAnnotationForm.is_applicable(self):
            #         return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.CustomAssayAnnotationForm:
            #     if wf.OCMAnnotationForm.is_applicable(self):
            #         return wf.OCMAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OligoMuxAnnotationForm.is_applicable(self):
            #         return wf.OligoMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.FlexAnnotationForm.is_applicable(self):
            #         return wf.FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseMuxAnnotationForm.is_applicable(self):
            #         return wf.ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.PooledLibraryAnnotationForm.is_applicable(self):
            #         return wf.PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.FeatureAnnotationForm.is_applicable(self):
            #         return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OpenSTAnnotationForm.is_applicable(self):
            #         return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.VisiumAnnotationForm.is_applicable(self):
            #         return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.DefineMultiplexedSamplesForm:
            #     if wf.OligoMuxAnnotationForm.is_applicable(self):
            #         return wf.OligoMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OCMAnnotationForm.is_applicable(self):
            #         return wf.OCMAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.FlexAnnotationForm.is_applicable(self):
            #         return wf.FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseMuxAnnotationForm.is_applicable(self):
            #         return wf.ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.FeatureAnnotationForm.is_applicable(self):
            #         return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OpenSTAnnotationForm.is_applicable(self):
            #         return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.VisiumAnnotationForm.is_applicable(self):
            #         return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.PooledLibraryAnnotationForm:
            #     return wf.PoolMappingForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.PoolMappingForm:
            #     if wf.BarcodeInputForm.is_applicable(self):
            #         return wf.BarcodeInputForm(seq_request=self.seq_request, uuid=self.uuid,)
            #     elif wf.TENXATACBarcodeInputForm.is_applicable(self):
            #         return wf.TENXATACBarcodeInputForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.BarcodeInputForm:
            #     if wf.BarcodeMatchForm.is_applicable(self):
            #         return wf.BarcodeMatchForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.TENXATACBarcodeInputForm.is_applicable(self):
            #         return wf.TENXATACBarcodeInputForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.FeatureAnnotationForm.is_applicable(self):
            #         return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OpenSTAnnotationForm.is_applicable(self):
            #         return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.VisiumAnnotationForm.is_applicable(self):
            #         return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.TENXATACBarcodeInputForm:
            #     if wf.BarcodeMatchForm.is_applicable(self):
            #         return wf.BarcodeMatchForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.FeatureAnnotationForm.is_applicable(self):
            #         return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OpenSTAnnotationForm.is_applicable(self):
            #         return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.VisiumAnnotationForm.is_applicable(self):
            #         return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.FeatureAnnotationForm:
            #     if wf.OpenSTAnnotationForm.is_applicable(self):
            #         return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.VisiumAnnotationForm.is_applicable(self):
            #         return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.VisiumAnnotationForm:
            #     if wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.ParseCRISPRGuideAnnotationForm:
            #     return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.OpenSTAnnotationForm:
            #     if wf.VisiumAnnotationForm.is_applicable(self):
            #         return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.BarcodeMatchForm:
            #     if wf.FeatureAnnotationForm.is_applicable(self):
            #         return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OpenSTAnnotationForm.is_applicable(self):
            #         return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.VisiumAnnotationForm.is_applicable(self):
            #         return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.FlexAnnotationForm:
            #     if self.seq_request.submission_type.id == C.SubmissionType.POOLED_LIBRARIES.id:
            #         return wf.PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseMuxAnnotationForm.is_applicable(self):
            #         return wf.ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.FeatureAnnotationForm.is_applicable(self):
            #         return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OpenSTAnnotationForm.is_applicable(self):
            #         return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.VisiumAnnotationForm.is_applicable(self):
            #         return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.OCMAnnotationForm:
            #     if wf.FlexAnnotationForm.is_applicable(self):
            #         return wf.FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseMuxAnnotationForm.is_applicable(self):
            #         return wf.ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif self.seq_request.submission_type.id == C.SubmissionType.POOLED_LIBRARIES.id:
            #         return wf.PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.FeatureAnnotationForm.is_applicable(self):
            #         return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OpenSTAnnotationForm.is_applicable(self):
            #         return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.VisiumAnnotationForm.is_applicable(self):
            #         return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.OligoMuxAnnotationForm:
            #     if self.seq_request.submission_type.id == C.SubmissionType.POOLED_LIBRARIES.id:
            #         return wf.PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OCMAnnotationForm.is_applicable(self):
            #         return wf.OCMAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.FlexAnnotationForm.is_applicable(self):
            #         return wf.FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseMuxAnnotationForm.is_applicable(self):
            #         return wf.ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.FeatureAnnotationForm.is_applicable(self):
            #         return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OpenSTAnnotationForm.is_applicable(self):
            #         return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.VisiumAnnotationForm.is_applicable(self):
            #         return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            # case wf.ParseMuxAnnotationForm:
            #     if self.seq_request.submission_type.id == C.SubmissionType.POOLED_LIBRARIES.id:
            #         return wf.PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.FeatureAnnotationForm.is_applicable(self):
            #         return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.OpenSTAnnotationForm.is_applicable(self):
            #         return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.VisiumAnnotationForm.is_applicable(self):
            #         return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
            #         return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            #     else:
            #         return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
                    

        raise ValueError(f"Could not infer next step for ({self.__class__})")

    def add_comment(self, context: str, text: str) -> None:
        if "comments" not in self.metadata:
            self.metadata["comments"] = []
        self.metadata["comments"].append({"context": context, "comment": text})