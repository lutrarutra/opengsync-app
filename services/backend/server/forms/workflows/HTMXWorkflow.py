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

    @property
    def previous_url(self) -> str | None:
        return self.metadata.get("previous_url")

    @previous_url.setter
    def previous_url(self, value: str | URL | None) -> None:
        if isinstance(value, URL):
            value = value.__str__()
        self.metadata["previous_url"] = value

    def init_step(self, step_name: str) -> None:
        """Initialize a new step in the workflow.

        When switching to a new step that has no existing data in Redis,
        the current step's tables and metadata are copied forward so that
        each step inherits all accumulated data from previous steps.
        """
        # Save the current step's data before switching away from it
        if hasattr(self, 'tables'):
            self.tables.save()
        if hasattr(self, 'metadata'):
            self.metadata.save()

        # Keep references to the current step's data for copying forward
        old_tables = getattr(self, 'tables', None)
        old_metadata = getattr(self, 'metadata', None)

        self.tables = msf_helpers.CachedFrameContainer(prefix=f"{self.key_prefix}:{step_name}:tables", r=self.r)
        self.metadata = msf_helpers.CachedDictionary(prefix=f"{self.key_prefix}:{step_name}:metadata", r=self.r)

        # If the new step has no existing data, inherit from the previous step.
        # If we are moving forward (POST/PUT request), always copy and overwrite to propagate changes.
        from ...core.context import ctx
        try:
            is_forward = ctx.request.method in ("POST", "PUT")
        except Exception:
            is_forward = False

        if old_tables is not None and (len(self.tables.keys()) == 0 or is_forward):
            for key in old_tables.keys():
                self.tables[key] = old_tables[key].copy()

        if old_metadata is not None and (len(self.metadata) == 0 or is_forward):
            self.metadata.update(dict(old_metadata.items()))

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

    def complete(self) -> None:
        # delete all keys associated with this workflow in Redis
        self.r.delete_pattern(f"{self.key_prefix}:*")

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
