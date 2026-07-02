import json
from uuid import uuid7
from typing import TypeAlias, Callable

from fastapi import Depends, Query

from ...core import dependencies, msf_helpers, redis

WorkflowFunc: TypeAlias = Callable[..., "HTMXWorkflow"]

class HTMXWorkflow:
    name: str
    def __init__(
        self,
        uuid: str | None,
        r: redis.RedisClient
    ):
        self.uuid = uuid or uuid7().__str__()
        self.r = r
        self.key_prefix = f"{self.name}:{self.uuid}"
        self.__steps: list[str] | None = None

        self.header = msf_helpers.CachedDictionary(
            template=f"{self.key_prefix}:{{step}}:header",
            r=r, steps=self.steps
        )

        self.tables = msf_helpers.MSFTableHandler(
            template=f"{self.key_prefix}:{{step}}:tables:{{table}}",
            r=r, steps=self.steps,
        )

        self.metadata = msf_helpers.CachedDictionary(
            template=f"{self.key_prefix}:{{step}}:metadata",
            r=r, steps=self.steps,
        )

    @property
    def steps(self) -> list[str]:
        if self.__steps is None:
            self.__steps = self.get_steps(f"{self.key_prefix}:steps")
        return self.__steps

    def get_steps(self, key: str) -> list[str]:
        data = self.r.get(key)
        if data is None:
            return []
        return json.loads(data.decode("utf-8"))  # type: ignore[no-any-return]

    def add(self, step_name: str) -> None:
        if self.__steps is None:
            self.__steps = self.get_steps(f"{self.key_prefix}:steps")
        
        if step_name in self.__steps:
            return
        
        self.__steps.append(step_name)
        self.set_steps(self.__steps)

    def set_steps(self, steps: list[str]) -> None:        
        self.r.set(f"{self.key_prefix}:steps", json.dumps(steps).encode('utf-8'), ex=self.r.ttl_hours * 3600)

    def pop_last(self) -> str | None:
        if not (steps := self.steps):
            return None
        last = steps.pop()
        self.set_steps(steps)
        self.__steps = steps
        return last

    @classmethod
    def Init(
        cls,
    ) -> WorkflowFunc:
        def dependency(
            uuid: str | None = Query(None, description="The UUID of the workflow state."),
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "HTMXWorkflow":
            uuid = uuid or uuid7().__str__()
            return cls(uuid=uuid, r=r)
        return dependency