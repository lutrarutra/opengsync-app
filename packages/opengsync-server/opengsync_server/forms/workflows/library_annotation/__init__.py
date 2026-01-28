from typing import TYPE_CHECKING

from .ProjectSelectForm import ProjectSelectForm
from .SelectServiceForm import SelectServiceForm
from .SampleAnnotationForm import SampleAnnotationForm
from .DefineMultiplexedSamplesForm import DefineMultiplexedSamplesForm
from .CustomAssayAnnotationForm import CustomAssayAnnotationFrom
from .PooledLibraryAnnotationForm import PooledLibraryAnnotationForm
from .PoolMappingForm import PoolMappingForm  
from .BarcodeInputForm import BarcodeInputForm
from .TENXATACBarcodeInputForm import TENXATACBarcodeInputForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .OligoMuxAnnotationForm import OligoMuxAnnotationForm  
from .FeatureAnnotationForm import FeatureAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from .CompleteSASForm import CompleteSASForm
from .BarcodeMatchForm import BarcodeMatchForm
from .OCMAnnotationForm import OCMAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm
from .ParseCRISPRGuideAnnotationForm import ParseCRISPRGuideAnnotationForm
from .ParseMuxAnnotationForm import ParseMuxAnnotationForm


if TYPE_CHECKING:
    from ... import MultiStepForm


_steps: list[type["MultiStepForm"]] = [
    ProjectSelectForm,
    SampleAnnotationForm,
    SampleAttributeAnnotationForm,
    SelectServiceForm,

    # if multiplexed ->
    DefineMultiplexedSamplesForm,
    CustomAssayAnnotationFrom,
    OligoMuxAnnotationForm,
    OCMAnnotationForm,
    FlexAnnotationForm,
    ParseMuxAnnotationForm,
    
    # if pooled ->
    PooledLibraryAnnotationForm,
    PoolMappingForm,
    BarcodeInputForm,
    BarcodeMatchForm,
    TENXATACBarcodeInputForm,

    # optional assays ->
    FeatureAnnotationForm,
    OpenSTAnnotationForm,
    VisiumAnnotationForm,
    ParseCRISPRGuideAnnotationForm,

    CompleteSASForm,
]

steps = dict([(s._step_name, s) for s in _steps])