import json
import time
from uuid import uuid7
from dataclasses import dataclass, asdict, fields
from typing import TypeAlias, Callable, Literal
from abc import ABC, abstractmethod

from starlette.datastructures import URL

from ...core import msf_helpers, redis

WorkflowFunc: TypeAlias = Callable[..., "HTMXWorkflow"]
StepMode: TypeAlias = Literal["forward", "back"]


@dataclass
class WorkflowRun:
    """Registry record of an unfinished run, stored at ``{key_prefix}:run``.

    ``step`` is the step last shown and ``step_mode`` how it was reached: "forward" (rendered
    fresh after submitting the step before it) or "back" (its 'Previous' route, prefilled with
    what it was submitted with). The step tracker can't tell: it keeps every step ever reached.
    """
    uuid: str
    context: str
    started_by_id: int
    started_at: float
    last_active_by_id: int
    last_active_at: float
    step: str
    step_mode: StepMode
    label: str | None = None
    steps_completed: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowRun":
        return cls(**{f.name: data[f.name] for f in fields(cls) if f.name in data})


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
        self._run: WorkflowRun | None = None
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
        if (run := self.run) is not None:
            self.r.zrem(self._index_key(run.context), self.uuid)
            self._run = None
        # delete all keys associated with this workflow in Redis
        self.r.delete_pattern(f"{self.key_prefix}:*")

    # ── Run registry ───────────────────────────────────────────────────
    # A registered run is listed in a sorted set per context (e.g. one sequencing request),
    # scored by its last activity. Every touch refreshes the TTL of all of the run's keys
    # together, so a run expires as a unit exactly one TTL after its last activity, which is
    # when ``unfinished_runs`` stops listing it. Entries whose run is gone anyway (completed
    # elsewhere, flushed) are dropped when listing.

    @classmethod
    def _index_key(cls, context: str) -> str:
        return f"WorkflowIndex:{cls.__name__}:{context}"

    @property
    def _run_key(self) -> str:
        return f"{self.key_prefix}:run"

    @property
    def run(self) -> WorkflowRun | None:
        """The registry record, or None when the run was never registered (or has expired)."""
        if self._run is None:
            self._run = self.load_run(self.r, self.uuid)
        return self._run

    def register(
        self, context: str, user_id: int, label: str | None = None,
        started_by_id: int | None = None, started_at: float | None = None,
    ) -> WorkflowRun:
        """List this run as unfinished under ``context``; ``started_*`` carry over a replaced run.

        Registering a run again (e.g. its first step re-submitted) keeps who started it and when.
        """
        now = time.time()
        if (existing := self.run) is not None:
            started_by_id = started_by_id if started_by_id is not None else existing.started_by_id
            started_at = started_at if started_at is not None else existing.started_at
        self._run = WorkflowRun(
            uuid=self.uuid, context=context,
            started_by_id=started_by_id if started_by_id is not None else user_id,
            started_at=started_at if started_at is not None else now,
            last_active_by_id=user_id, last_active_at=now,
            step=self.current_step, step_mode="forward", label=label,
        )
        self._persist_run()
        return self._run

    def touch(self, user_id: int, step: str | None = None, step_mode: StepMode | None = None) -> None:
        """Record activity on a registered run and keep all of its keys alive."""
        if (run := self.run) is None:
            return
        run.last_active_by_id = user_id
        run.last_active_at = time.time()
        if step is not None:
            run.step = step
            # Steps submitted on the way to it: the ones before it in the tracker
            steps = self.step_tracker.steps
            run.steps_completed = steps.index(step) if step in steps else len(steps)
        if step_mode is not None:
            run.step_mode = step_mode
        self._persist_run()

    def _persist_run(self) -> None:
        assert self._run is not None
        ttl = self.r.ttl_hours * 3600
        index_key = self._index_key(self._run.context)
        with self.r.pipeline() as pipe:
            pipe.set(self._run_key, json.dumps(asdict(self._run)).encode("utf-8"), ex=ttl)
            pipe.zadd(index_key, {self.uuid: self._run.last_active_at})
            pipe.expire(index_key, ttl)
            for key in self.r.scan_iter(match=f"{self.key_prefix}:*"):
                pipe.expire(key, ttl)
            pipe.execute()

    @classmethod
    def load_run(cls, r: redis.RedisClient, uuid: str) -> WorkflowRun | None:
        """The registry record of a run, without loading the run's state."""
        if (data := r.get_dict(f"{cls.__name__}:{uuid}:run")) is None:
            return None
        return WorkflowRun.from_dict(data)

    @classmethod
    def unfinished_runs(cls, r: redis.RedisClient, context: str) -> list[WorkflowRun]:
        """Registered runs of ``context`` that have not expired, most recently active first."""
        index_key = cls._index_key(context)
        r.zremrangebyscore(index_key, "-inf", time.time() - r.ttl_hours * 3600)
        runs: list[WorkflowRun] = []
        for uuid in r.zrevrange(index_key, 0, -1):
            uuid = uuid.decode("utf-8")
            if (run := cls.load_run(r, uuid)) is None:
                r.zrem(index_key, uuid)
                continue
            runs.append(run)
        return runs

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
