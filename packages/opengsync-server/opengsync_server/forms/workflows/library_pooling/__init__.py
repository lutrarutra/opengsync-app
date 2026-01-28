from typing import TYPE_CHECKING

from .LibraryPoolingForm import LibraryPoolingForm
from .CompleteLibraryPoolingForm import CompleteLibraryPoolingForm


if TYPE_CHECKING:
    from ... import MultiStepForm


_steps: list[type["MultiStepForm"]] = [
    LibraryPoolingForm,
    CompleteLibraryPoolingForm,
]

steps = dict([(s._step_name, s) for s in _steps])