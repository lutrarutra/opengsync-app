
from opengsync_db import models, categories as cats

from ... import MultiStepForm
from .. import library_annotation as wf

class LibraryAnnotationWorkflow(MultiStepForm):
    _workflow_name = "library_annotation"
    
    def __init__(self, seq_request: models.SeqRequest, step_name: str, formdata: dict | None = None, uuid: str | None = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, step_name=step_name,
            workflow=LibraryAnnotationWorkflow._workflow_name, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

    def get_next_step(self) -> "MultiStepForm":
        match self.__class__:
            case wf.ProjectSelectForm:
                return wf.SampleAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.SampleAnnotationForm:
                return wf.SampleAttributeAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.SampleAttributeAnnotationForm:
                return wf.SelectServiceForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.SelectServiceForm:
                if self.seq_request.submission_type.id == cats.SubmissionType.POOLED_LIBRARIES.id:
                    return wf.PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.CustomAssayAnnotationForm:
                if wf.OCMAnnotationForm.is_applicable(self):
                    return wf.OCMAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OligoMuxAnnotationForm.is_applicable(self):
                    return wf.OligoMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.FlexAnnotationForm.is_applicable(self):
                    return wf.FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseMuxAnnotationForm.is_applicable(self):
                    return wf.ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.PooledLibraryAnnotationForm.is_applicable(self):
                    return wf.PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.DefineMultiplexedSamplesForm:
                if wf.OligoMuxAnnotationForm.is_applicable(self):
                    return wf.OligoMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OCMAnnotationForm.is_applicable(self):
                    return wf.OCMAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.FlexAnnotationForm.is_applicable(self):
                    return wf.FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseMuxAnnotationForm.is_applicable(self):
                    return wf.ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.PooledLibraryAnnotationForm:
                return wf.PoolMappingForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.PoolMappingForm:
                if wf.BarcodeInputForm.is_applicable(self):
                    return wf.BarcodeInputForm(seq_request=self.seq_request, uuid=self.uuid,)
                elif wf.TENXATACBarcodeInputForm.is_applicable(self):
                    return wf.TENXATACBarcodeInputForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.BarcodeInputForm:
                if wf.BarcodeMatchForm.is_applicable(self):
                    return wf.BarcodeMatchForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.TENXATACBarcodeInputForm.is_applicable(self):
                    return wf.TENXATACBarcodeInputForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.TENXATACBarcodeInputForm:
                if wf.BarcodeMatchForm.is_applicable(self):
                    return wf.BarcodeMatchForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.FeatureAnnotationForm:
                if wf.OpenSTAnnotationForm.is_applicable(self):
                    return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.VisiumAnnotationForm:
                if wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.ParseCRISPRGuideAnnotationForm:
                return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.OpenSTAnnotationForm:
                if wf.VisiumAnnotationForm.is_applicable(self):
                    return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.BarcodeMatchForm:
                if wf.FeatureAnnotationForm.is_applicable(self):
                    return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.FlexAnnotationForm:
                if self.seq_request.submission_type.id == cats.SubmissionType.POOLED_LIBRARIES.id:
                    return wf.PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseMuxAnnotationForm.is_applicable(self):
                    return wf.ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.OCMAnnotationForm:
                if wf.FlexAnnotationForm.is_applicable(self):
                    return wf.FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseMuxAnnotationForm.is_applicable(self):
                    return wf.ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif self.seq_request.submission_type.id == cats.SubmissionType.POOLED_LIBRARIES.id:
                    return wf.PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.OligoMuxAnnotationForm:
                if self.seq_request.submission_type.id == cats.SubmissionType.POOLED_LIBRARIES.id:
                    return wf.PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OCMAnnotationForm.is_applicable(self):
                    return wf.OCMAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.FlexAnnotationForm.is_applicable(self):
                    return wf.FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseMuxAnnotationForm.is_applicable(self):
                    return wf.ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
            case wf.ParseMuxAnnotationForm:
                if self.seq_request.submission_type.id == cats.SubmissionType.POOLED_LIBRARIES.id:
                    return wf.PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.FeatureAnnotationForm.is_applicable(self):
                    return wf.FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.OpenSTAnnotationForm.is_applicable(self):
                    return wf.OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.VisiumAnnotationForm.is_applicable(self):
                    return wf.VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                elif wf.ParseCRISPRGuideAnnotationForm.is_applicable(self):
                    return wf.ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
                else:
                    return wf.CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
                    

        raise ValueError(f"Could not infer next step for {self._step_name} ({self.__class__})")