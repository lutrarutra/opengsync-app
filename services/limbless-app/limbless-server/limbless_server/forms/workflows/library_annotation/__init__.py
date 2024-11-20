from typing import TYPE_CHECKING

from .ProjectSelectForm import ProjectSelectForm  # noqa: F401
from .SpecifyAssayForm import SpecifyAssayForm  # noqa: F401
from .DefineSamplesForm import DefineSamplesForm  # noqa: F401
from .DefineMultiplexedSamplesForm import DefineMultiplexedSamplesForm  # noqa: F401
from .LibraryAnnotationForm import LibraryAnnotationForm  # noqa: F401
from .PooledLibraryAnnotationForm import PooledLibraryAnnotationForm  # noqa: F401
from .PoolMappingForm import PoolMappingForm    # noqa: F401
from .BarcodeInputForm import BarcodeInputForm  # noqa: F401
from .IndexKitMappingForm import IndexKitMappingForm  # noqa: F401
from .VisiumAnnotationForm import VisiumAnnotationForm  # noqa: F401
from .CMOAnnotationForm import CMOAnnotationForm    # noqa: F401
from .KitMappingForm import KitMappingForm    # noqa: F401
from .FeatureAnnotationForm import FeatureAnnotationForm  # noqa: F401
from .FRPAnnotationForm import FRPAnnotationForm  # noqa: F401
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm  # noqa: F401
from .CompleteSASForm import CompleteSASForm  # noqa: F401


if TYPE_CHECKING:
    from ... import MultiStepForm


_steps: list[type["MultiStepForm"]] = [
    ProjectSelectForm,
    SpecifyAssayForm,
    DefineSamplesForm,
    DefineMultiplexedSamplesForm,
    LibraryAnnotationForm,
    PooledLibraryAnnotationForm,
    PoolMappingForm,
    BarcodeInputForm,
    IndexKitMappingForm,
    VisiumAnnotationForm,
    CMOAnnotationForm,
    KitMappingForm,
    FeatureAnnotationForm,
    FRPAnnotationForm,
    SampleAttributeAnnotationForm,
    CompleteSASForm,
]

steps = dict([(s._step_name, s) for s in _steps])