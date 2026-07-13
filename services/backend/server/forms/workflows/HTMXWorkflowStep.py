from abc import ABC

from ..HTMXForm import HTMXForm
from .HTMXWorkflow import HTMXWorkflow

class HTMXWorkflowStep(HTMXForm, ABC):
    def __init__(self, workflow: "HTMXWorkflow") -> None:
        super().__init__()
        self.workflow = workflow
        self.workflow.init_step(self.__class__.__name__)

    @property
    def previous_url(self) -> str | None:
        return self.workflow.previous_url

    def is_applicable(self) -> bool:
        return True