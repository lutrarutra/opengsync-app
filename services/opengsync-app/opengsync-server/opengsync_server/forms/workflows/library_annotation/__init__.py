from typing import TYPE_CHECKING

from .ProjectSelectForm import ProjectSelectForm  # noqa: F401
from .SelectAssayForm import SelectAssayForm  # noqa: F401
from .SampleAnnotationForm import SampleAnnotationForm  # noqa: F401
from .DefineMultiplexedSamplesForm import DefineMultiplexedSamplesForm  # noqa: F401
from .CustomAssayAnnotationForm import CustomAssayAnnotationFrom  # noqa: F401
from .PooledLibraryAnnotationForm import PooledLibraryAnnotationForm  # noqa: F401
from .PoolMappingForm import PoolMappingForm    # noqa: F401
from .BarcodeInputForm import BarcodeInputForm  # noqa: F401
from .TENXATACBarcodeInputForm import TENXATACBarcodeInputForm  # noqa: F401
from .VisiumAnnotationForm import VisiumAnnotationForm  # noqa: F401
from .OligoMuxAnnotationForm import OligoMuxAnnotationForm    # noqa: F401
from .FeatureAnnotationForm import FeatureAnnotationForm  # noqa: F401
from .FlexAnnotationForm import FlexAnnotationForm  # noqa: F401
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm  # noqa: F401
from .CompleteSASForm import CompleteSASForm  # noqa: F401
from .BarcodeMatchForm import BarcodeMatchForm  # noqa: F401
from .OCMAnnotationForm import OCMAnnotationForm  # noqa: F401
from .OpenSTAnnotationForm import OpenSTAnnotationForm  # noqa: F401
from .ParseCRISPRGuideAnnotationForm import ParseCRISPRGuideAnnotationForm  # noqa: F401
from .ParseMuxAnnotationForm import ParseMuxAnnotationForm  # noqa: F401


if TYPE_CHECKING:
    from ... import MultiStepForm


_steps: list[type["MultiStepForm"]] = [
    ProjectSelectForm,
    SampleAnnotationForm,
    SampleAttributeAnnotationForm,
    SelectAssayForm,

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