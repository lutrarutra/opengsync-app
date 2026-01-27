from typing import TYPE_CHECKING

from .BarcodeInputForm import BarcodeInputForm
from .TENXATACBarcodeInputForm import TENXATACBarcodeInputForm
from .BarcodeMatchForm import BarcodeMatchForm
from .CompleteReindexForm import CompleteReindexForm

if TYPE_CHECKING:
    from ... import MultiStepForm

_steps: list[type["MultiStepForm"]] = [
    BarcodeInputForm,
    TENXATACBarcodeInputForm,
    BarcodeMatchForm,
    CompleteReindexForm,
]

steps = dict([(s._step_name, s) for s in _steps])