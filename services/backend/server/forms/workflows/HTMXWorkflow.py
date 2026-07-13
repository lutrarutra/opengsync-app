from uuid import uuid7
from typing import TypeAlias, Callable
from abc import ABC, abstractmethod

from starlette.datastructures import URL

from ...core import msf_helpers, redis

WorkflowFunc: TypeAlias = Callable[..., "HTMXWorkflow"]

class HTMXWorkflow(ABC):
    def __init__(
        self,
        uuid: str | None,
        r: redis.RedisClient,
        step: str | None = None,
    ):
        self.uuid = uuid or uuid7().__str__()
        self.r = r
        self.key_prefix = f"{self.__class__.__name__}:{self.uuid}"
        self.step_tracker = msf_helpers.StepTracker(prefix=f"{self.key_prefix}:steps", r=r)
        self.___current_step = step

        self.header = msf_helpers.CachedDictionary(prefix=f"{self.key_prefix}:header", r=r)
        self.init_step(self.current_step)

        print(f"Initialized workflow {self.__class__.__name__} with UUID {self.uuid}, current step: {self.current_step}")

    @property
    def previous_url(self) -> str | None:
        return self.metadata.get("previous_url")

    @previous_url.setter
    def previous_url(self, value: str | URL | None) -> None:
        if isinstance(value, URL):
            value = value.__str__()
        self.metadata["previous_url"] = value

    def init_step(self, step_name: str) -> None:
        """Initialize a new step in the workflow."""
        self.tables = msf_helpers.CachedFrameContainer(prefix=f"{self.key_prefix}:{step_name}:tables", r=self.r)
        self.metadata = msf_helpers.CachedDictionary(prefix=f"{self.key_prefix}:{step_name}:metadata", r=self.r)

    @property
    def current_step(self) -> str:
        if self.___current_step is None:
            steps = self.step_tracker.steps
            self.___current_step = steps[-1] if steps else None
        if self.___current_step is None:
            raise ValueError("Current step is not set. Ensure that at least one step has been added to the workflow.")
        return self.___current_step

    @property
    def previous_step(self) -> str | None:
        steps = self.step_tracker.steps
        return steps[-2] if len(steps) > 1 else None

    def add_step(self, step_name: str) -> None:
        self.step_tracker.add(step_name)
        self.save()

    def pop_step(self) -> str | None:
        return self.step_tracker.pop()

    def save(self) -> None:
        self.header.save()
        self.tables.save()
        self.metadata.save()

    @classmethod
    @abstractmethod
    def Init(
        cls,
    ) -> WorkflowFunc:
        # def dependency(
        #     uuid: str | None = Query(None, description="The UUID of the workflow state."),
        #     r: redis.RedisClient = Depends(dependencies.redis),
        # ) -> "HTMXWorkflow":
        #     uuid = uuid or uuid7().__str__()
        #     return cls(uuid=uuid, r=r)
        ...
