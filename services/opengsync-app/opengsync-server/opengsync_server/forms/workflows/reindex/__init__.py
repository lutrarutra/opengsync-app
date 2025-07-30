from typing import TYPE_CHECKING

from .BarcodeInputForm import BarcodeInputForm  # noqa
from .IndexKitMappingForm import IndexKitMappingForm  # noqa
from .TENXATACBarcodeInputForm import TENXATACBarcodeInputForm  # noqa
from .BarcodeMatchForm import BarcodeMatchForm  # noqa
from .CompleteReindexForm import CompleteReindexForm  # noqa

if TYPE_CHECKING:
    from ... import MultiStepForm

_steps: list[type["MultiStepForm"]] = [
    BarcodeInputForm,
    TENXATACBarcodeInputForm,
    IndexKitMappingForm,
    BarcodeMatchForm,
    CompleteReindexForm,
]

steps = dict([(s._step_name, s) for s in _steps])