from typing import TYPE_CHECKING

from .BarcodeInputForm import BarcodeInputForm  # noqa: F401
from .IndexKitMappingForm import IndexKitMappingForm  # noqa: F401
from .CompleteLibraryPoolingForm import CompleteLibraryPoolingForm  # noqa: F401


if TYPE_CHECKING:
    from ... import MultiStepForm


_steps: list[type["MultiStepForm"]] = [
    BarcodeInputForm,
    IndexKitMappingForm,
    CompleteLibraryPoolingForm,
]

steps = dict([(s._step_name, s) for s in _steps])