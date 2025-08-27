from typing import TYPE_CHECKING

from .ProjectSelectForm import ProjectSelectForm  # noqa: F401
from .SelectAssayForm import SelectAssayForm  # noqa: F401
from .DefineSamplesForm import DefineSamplesForm  # noqa: F401
from .DefineMultiplexedSamplesForm import DefineMultiplexedSamplesForm  # noqa: F401
from .LibraryAnnotationForm import LibraryAnnotationForm  # noqa: F401
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


if TYPE_CHECKING:
    from ... import MultiStepForm


_steps: list[type["MultiStepForm"]] = [
    ProjectSelectForm,
    SelectAssayForm,
    DefineSamplesForm,
    DefineMultiplexedSamplesForm,
    LibraryAnnotationForm,
    PooledLibraryAnnotationForm,
    PoolMappingForm,
    BarcodeInputForm,
    BarcodeMatchForm,
    TENXATACBarcodeInputForm,
    VisiumAnnotationForm,
    OligoMuxAnnotationForm,
    FeatureAnnotationForm,
    FlexAnnotationForm,
    SampleAttributeAnnotationForm,
    CompleteSASForm,
    OCMAnnotationForm,
    OpenSTAnnotationForm
]

steps = dict([(s._step_name, s) for s in _steps])