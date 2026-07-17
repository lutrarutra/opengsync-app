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
        self._active_step: str | None = None

        self.header = msf_helpers.CachedDictionary(prefix=f"{self.key_prefix}:header", r=r)
        self.init_step(step or self.step_tracker.last() or self.__class__.__name__)

    def _step_prefix(self, step_name: str) -> str:
        """Return the Redis key prefix for a given step's data."""
        return f"{self.key_prefix}:{step_name}"

    @property
    def previous_url(self) -> str | None:
        return self.metadata.get("previous_url")

    @previous_url.setter
    def previous_url(self, value: str | URL | None) -> None:
        if isinstance(value, URL):
            value = value.__str__()
        self.metadata["previous_url"] = value

    # ── Step lifecycle ─────────────────────────────────────────────────

    def init_step(self, step_name: str) -> None:
        """Initialize (or switch to) a workflow step.

        Behaviour:
        - If already on ``step_name``, this is a no-op (prevents double-init
          from ``HTMXWorkflow.__init__`` + ``HTMXWorkflowStep.__init__``).
        - The current step's data is saved to Redis before switching.
        - If the destination step has **no existing data** in Redis, or if
          the request is a forward navigation (POST/PUT), data from the
          **previous step** (the last tracker entry that is not the current
          step) is copied to the destination via Redis-native ``COPY``.
        - On forward navigation, the destination is cleared first so that
          edits made in the current step propagate to the next step.
        """
        if self._active_step == step_name:
            return

        # Save current step's data before switching
        if self._active_step is not None:
            self.tables.save()
            self.metadata.save()

        # Determine the previous step *before* switching
        prev_step = self._active_step

        # Switch to the new step
        sp = self._step_prefix(step_name)
        self.tables = msf_helpers.CachedFrameContainer(prefix=f"{sp}:tables", r=self.r)
        self.metadata = msf_helpers.CachedDictionary(prefix=f"{sp}:metadata", r=self.r)
        self._active_step = step_name

        # Decide whether to copy data from the previous step
        from ...core.context import ctx
        try:
            is_forward = ctx.request.method in ("POST", "PUT")
        except Exception:
            is_forward = False

        dest_empty = len(self.tables.keys()) == 0 and len(self.metadata) == 0
        should_copy = prev_step is not None and (dest_empty or is_forward)

        if should_copy:
            assert prev_step is not None  # guaranteed by should_copy guard
            prev_sp = self._step_prefix(prev_step)
            if is_forward:
                self.tables.clear()
                self.metadata.clear()
            self.tables.copy_from(f"{prev_sp}:tables")
            self.metadata.copy_from(f"{prev_sp}:metadata")

    @property
    def current_step(self) -> str:
        if self._active_step is not None:
            return self._active_step
        last = self.step_tracker.last()
        if last is not None:
            return last
        raise ValueError("Current step is not set. Ensure that at least one step has been added to the workflow.")

    @property
    def previous_step(self) -> str | None:
        """Return the most recent step in the tracker that is not the current step."""
        for step in reversed(self.step_tracker.steps):
            if step != self._active_step:
                return step
        return None

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
