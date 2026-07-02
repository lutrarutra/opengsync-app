from fastapi import Request, Response, Query, Depends, APIRouter

from opengsync_db import models, categories as C, SyncSession

from ....core import dependencies, exceptions as exc, redis
from ..HTMXWorkflow import HTMXWorkflow, WorkflowFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import HTMXForm, RouteFunc, FormFunc
from .. import library_annotation as wf

class LibraryAnnotationWorkflow(HTMXWorkflow):
    name = "library-annotation"
    
    def __init__(self, r: redis.RedisClient, seq_request_id: int, uuid: str | None = None):
        super().__init__(uuid=uuid, r=r)
        self.seq_request_id = seq_request_id

    @classmethod
    def Init(
        cls,
    ) -> WorkflowFunc:
        def dependency(
            seq_request_id: int,
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "LibraryAnnotationWorkflow":
            return cls(uuid=uuid, r=r, seq_request_id=seq_request_id)
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
        router.add_api_route("/begin", wf.LibraryAnnotationWorkflow.Begin(), methods=["GET"], name="LibraryAnnotationWorkflow.begin")
        router.include_router(wf.ProjectSelectForm.Router("LibraryAnnotationWorkflow"))
        return router

    def get_next_step(self, current_step: str) -> "HTMXWorkflowStep":
        match current_step:
            case "project_select":
                return wf.SampleAnnotationForm(request=request, workflow=self)
            case "sample_annotation":
                return wf.SampleAttributeAnnotationForm(request=self.request, workflow=self)
            # case wf.SampleAttributeAnnotationForm:
            #     return wf.SelectServiceForm(seq_request=self.seq_request, uuid=self.uuid)
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
                    

        raise ValueError(f"Could not infer next step for {self.step_name} ({self.__class__})")