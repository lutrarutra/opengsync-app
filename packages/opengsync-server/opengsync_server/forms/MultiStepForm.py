from uuid_extensions import uuid7str

from .. import msf_cache, logger
from .HTMXFlaskForm import HTMXFlaskForm
from ..tools import MSFTableHandler, CachedDictionary


class StepTracker:
    def __init__(self, key: str):
        self.__steps: list[str] | None = None
        self.key = key

    @property
    def steps(self) -> list[str]:
        if self.__steps is None:
            self.__steps = msf_cache.get_steps(self.key)
        return self.__steps

    def add(self, step_name: str) -> None:
        if self.__steps is None:
            self.__steps = msf_cache.get_steps(self.key)
        
        if step_name in self.__steps:
            return
        
        self.__steps.append(step_name)
        msf_cache.set_steps(self.key, self.__steps)

    def pop_last(self) -> str | None:
        if not (steps := self.steps):
            return None
        last = steps.pop()
        msf_cache.set_steps(self.key, steps)
        self.__steps = steps
        return last
    
    def get_last(self) -> str | None:
        if not (steps := self.steps):
            return None
        return steps[-1]

class MultiStepForm(HTMXFlaskForm):
    _step_name: str
    _workflow_name: str

    def __init__(self, workflow: str, uuid: str | None, formdata: dict | None, step_name: str, step_args: dict):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        if uuid is None:
            uuid = uuid7str()

        self.step_name = step_name
        self.step_args = step_args
        self.uuid = uuid
        self.workflow = workflow

        self.steps = StepTracker(key=f"{self.workflow}:{self.uuid}:steps")
        self.step()
        steps = self.steps.steps
            
        self.header = CachedDictionary(template=f"{self.workflow}:{self.uuid}:{{step}}:header", msf_cache=msf_cache, steps=steps)

        self.tables = MSFTableHandler(
            template=f"{self.workflow}:{self.uuid}:{{step}}:tables:{{table}}", msf_cache=msf_cache, steps=steps
        )
        self.metadata = CachedDictionary(
            template=f"{self.workflow}:{self.uuid}:{{step}}:metadata", msf_cache=msf_cache, steps=steps
        )

    @staticmethod
    def PopLastStep(workflow: str, uuid: str) -> str | None:
        steps = StepTracker(key=f"{workflow}:{uuid}:steps")
        if (current_step := steps.pop_last()) is not None:
            msf_cache.delete_pattern(f"{workflow}:{uuid}:{current_step}:*")
        return steps.get_last()
    
    def get_previous_step(self) -> str | None:
        steps = self.steps.steps
        if len(steps) < 2:
            return None
        return steps[-2]

    def fill_previous_form(self):
        logger.warning(f"Workflow '{self.workflow}', step '{self.step_name}', fill_previous_form() not implemented in subclass...")

    def complete(self):
        msf_cache.delete_pattern(f"{self.workflow}:{self.uuid}:*")
    
    def add_comment(self, context: str, text: str):
        self.metadata["comment"] = {
            "context": context,
            "text": text,
        }

    def get_comments(self) -> list[dict]:
        comments = self.metadata.get("comments", [])
        if "comment" in self.metadata:
            comments.append(self.metadata["comment"])
        return comments

    def step(self):
        self.steps.add(self.step_name)
        
    def __str__(self) -> str:
        return f"MultiStepForm(workflow: {self.workflow}, step_name: {self.step_name}, uuid: {self.uuid})"
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def debug(self):
        logger.debug(f"Current Step: {self.step_name}\nSteps: {self.steps.steps}\nTables: {self.tables.keys()}\nMetadata: {list(self.metadata.keys())}\nHeader: {list(self.header.keys())}")