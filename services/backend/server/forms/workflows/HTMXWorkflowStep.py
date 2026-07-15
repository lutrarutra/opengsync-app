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

    @classmethod
    def is_applicable(cls, workflow: "HTMXWorkflow") -> bool:
        return True