from typing import TYPE_CHECKING

from .BarcodeInputForm import BarcodeInputForm  # noqa: F401
from .BarcodeMatchForm import BarcodeMatchForm  # noqa: F401
from .CompleteLibraryPoolingForm import CompleteLibraryPoolingForm  # noqa: F401
from .TENXATACBarcodeInputForm import TENXATACBarcodeInputForm  # noqa: F401


if TYPE_CHECKING:
    from ... import MultiStepForm


_steps: list[type["MultiStepForm"]] = [
    BarcodeInputForm,
    TENXATACBarcodeInputForm,
    BarcodeMatchForm,
    CompleteLibraryPoolingForm,
]

steps = dict([(s._step_name, s) for s in _steps])