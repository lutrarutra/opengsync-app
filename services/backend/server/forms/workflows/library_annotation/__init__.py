from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .ProjectSelectForm import ProjectSelectForm
from .SampleAnnotationForm import SampleAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm

_steps = [
    ProjectSelectForm,
    SampleAnnotationForm,
    SampleAttributeAnnotationForm,
]

steps = {s._step_name: s for s in _steps}

__all__ = [
    "LibraryAnnotationWorkflow",

    "ProjectSelectForm",
    "SampleAnnotationForm",
    "SampleAttributeAnnotationForm",
    "steps",
]
