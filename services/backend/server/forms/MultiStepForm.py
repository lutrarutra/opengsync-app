"""FastAPI port of the Flask ``MultiStepForm``.

This provides the same step-tracking, table caching, and metadata caching
that the Flask version does, but works with the async HTMXForm base class
instead of WTForms / ``HTMXFlaskForm``.

Subclasses should:
    1. Set ``_step_name`` and ``_workflow_name``.
    2. Accept ``request: Request`` as the first positional arg (inherited
       from ``HTMXForm``).
    3. Call ``MultiStepForm.__init__(self, request, ...)``.
    4. Override ``process_request() -> Response`` with the step logic.
"""

from __future__ import annotations

from fastapi import Request
from uuid6 import uuid7

from loguru import logger

from ..core.msf_cache import msf_cache
from ..core.msf_helpers import MSFTableHandler, CachedDictionary
from .HTMXForm import HTMXForm


class StepTracker:
    """Tracks the ordered list of step names visited during a workflow."""

    def __init__(self, key: str):
        self.__steps: list[str] | None = None
        self.key = key

    @property
    async def steps(self) -> list[str]:
        if self.__steps is None:
            self.__steps = await msf_cache.get_steps(self.key)
        return self.__steps

    async def add(self, step_name: str) -> None:
        if self.__steps is None:
            self.__steps = await msf_cache.get_steps(self.key)

        if step_name in self.__steps:
            return

        self.__steps.append(step_name)
        await msf_cache.set_steps(self.key, self.__steps)

    async def pop_last(self) -> str | None:
        steps = await self.steps
        if not steps:
            return None
        last = steps.pop()
        await msf_cache.set_steps(self.key, steps)
        self.__steps = steps
        return last

    async def get_last(self) -> str | None:
        steps = await self.steps
        if not steps:
            return None
        return steps[-1]


class MultiStepForm(HTMXForm):
    """Base class for multi-step workflow forms in FastAPI.

    Mirrors the Flask ``MultiStepForm`` but uses ``HTMXForm`` as the
    base and the async ``msf_cache`` for step / table / metadata storage.
    """

    _step_name: str
    _workflow_name: str

    def __init__(
        self,
        request: Request,
        workflow: str,
        uuid: str | None,
        step_name: str,
        step_args: dict,
    ) -> None:
        super().__init__(request)
        if uuid is None:
            uuid = uuid7().__str__()

        self.step_name = step_name
        self.step_args = step_args
        self.uuid = uuid
        self.workflow = workflow

        self.steps = StepTracker(key=f"{self.workflow}:{self.uuid}:steps")

    @classmethod
    async def create(cls, request: Request, workflow: str, uuid: str | None, step_name: str, step_args: dict) -> MultiStepForm:
        """Factory method to create an instance of the form and initialize its state in the cache."""
        form = cls(request, workflow, uuid, step_name, step_args)
        await form._init_msf_state()
        return form

    async def _init_msf_state(self) -> None:
        await self.steps.add(self.step_name)
        steps = await self.steps.steps

        self.header = CachedDictionary(
            template=f"{self.workflow}:{self.uuid}:{{step}}:header",
            msf_cache=msf_cache,
            steps=steps,
        )

        self.tables = MSFTableHandler(
            template=f"{self.workflow}:{self.uuid}:{{step}}:tables:{{table}}",
            msf_cache=msf_cache,
            steps=steps,
        )

        self.metadata = CachedDictionary(
            template=f"{self.workflow}:{self.uuid}:{{step}}:metadata",
            msf_cache=msf_cache,
            steps=steps,
        )

    @staticmethod
    async def PopLastStep(workflow: str, uuid: str) -> str | None:
        """Pop the last step from the tracker and clean up its cache."""
        steps = StepTracker(key=f"{workflow}:{uuid}:steps")
        current_step = await steps.pop_last()
        if current_step is not None:
            await msf_cache.delete_pattern(f"{workflow}:{uuid}:{current_step}:*")
        return await steps.get_last()

    async def get_previous_step(self) -> str | None:
        steps = await self.steps.steps
        if len(steps) < 2:
            return None
        return steps[-2]

    async def step(self) -> None:
        """Register the current step in the step tracker."""
        await self.steps.add(self.step_name)

    async def fill_previous_form(self) -> None:
        """Override in subclass to populate the form from the previous step's data."""
        logger.warning(
            f"Workflow '{self.workflow}', step '{self.step_name}', "
            f"fill_previous_form() not implemented in subclass…"
        )

    async def complete(self) -> None:
        """Mark the workflow as complete and clean up all cached state."""
        await msf_cache.delete_pattern(f"{self.workflow}:{self.uuid}:*")

    async def add_comment(self, context: str, text: str) -> None:
        current = await self.metadata.get("comment", {})
        current[context] = text
        await self.metadata.__setitem__("comment", current)

    async def get_comments(self) -> dict[str, str]:
        return await self.metadata.get("comment", {})

    async def debug(self) -> None:
        steps_list = await self.steps.steps
        table_keys = await self.tables.keys() if hasattr(self.tables, "keys") else []
        meta_keys = list(await self.metadata.keys()) if hasattr(self.metadata, "keys") else []
        header_keys = list(await self.header.keys()) if hasattr(self.header, "keys") else []

        logger.debug(
            f"Current Step: {self.step_name}\n"
            f"Steps: {steps_list}\n"
            f"Tables: {table_keys}\n"
            f"Metadata: {meta_keys}\n"
            f"Header: {header_keys}"
        )

    def __str__(self) -> str:
        return f"MultiStepForm(workflow: {self.workflow}, step_name: {self.step_name}, uuid: {self.uuid})"

    def __repr__(self) -> str:
        return self.__str__()
