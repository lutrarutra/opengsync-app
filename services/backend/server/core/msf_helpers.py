"""Async cached helpers for MultiStepForm state.

Ported from Flask ``tools.MSFTableHandler`` and ``tools.CachedDictionary``
to use the async ``msf_cache`` module.
"""

from __future__ import annotations

from typing import Any, Hashable

import pandas as pd
from redis.asyncio import Redis

from .msf_cache import MSFCache


class MSFTableHandler:
    """Dict-like interface for reading / writing DataFrames across workflow steps.

    Tables are looked up in the current step first, then walked backwards
    through earlier steps until a match is found.
    """

    def __init__(self, template: str, msf_cache: MSFCache, steps: list[str]):
        self.__tables: dict[str, pd.DataFrame] = {}
        self.template = template
        self.r = msf_cache
        self._steps_reversed = list(reversed(steps))  # oldest → newest
        self.current_step = steps[-1] if steps else ""

    def _key(self, step_name: str, table_name: str) -> str:
        return self.template.format(step=step_name, table=table_name)

    async def __getitem__(self, key: str) -> pd.DataFrame:
        if key in self.__tables:
            return self.__tables[key]

        for step in self._steps_reversed:
            table = await self.r.get_table(self._key(step, key))
            if table is not None:
                self.__tables[key] = table
                return table

        raise KeyError(f"Table '{key}' not found in any step.")

    async def __setitem__(self, key: str, table: pd.DataFrame) -> None:
        self.__tables[key] = table
        await self.r.set_table(self._key(self.current_step, key), table)

    async def get(self, key: str, step: str | None = None) -> pd.DataFrame | None:
        if step is not None:
            return await self.r.get_table(self._key(step, key))
        try:
            return await self[key]
        except KeyError:
            return None

    async def keys(self) -> list[str]:
        tables = list(self.__tables.keys())
        async with Redis(connection_pool=self.r._pool_or_raise()) as r:
            for step in self._steps_reversed:
                pattern = self.template.format(step=step, table="*")
                async for raw_key in r.scan_iter(match=pattern):
                    table_name = raw_key.decode("utf-8").split(":")[-1]
                    if table_name not in tables:
                        tables.append(table_name)
        return tables


class CachedDictionary:
    """Dict-like helper that persists to Redis per-step.

    Reads walk steps newest → oldest; writes go to the current step only.
    """

    def __init__(self, template: str, msf_cache: MSFCache, steps: list[str]):
        self.__data: dict | None = None
        self.template = template
        self.r = msf_cache
        self._steps_reversed = list(reversed(steps))
        self.current_step = steps[0] if steps else ""

    def _key(self, step_name: str) -> str:
        return self.template.format(step=step_name)

    async def _load(self) -> dict:
        if self.__data is None:
            for step in self._steps_reversed:
                d = await self.r.get_dict(self._key(step))
                if d is not None:
                    self.__data = d
                    break
            else:
                self.__data = {}
        return self.__data

    async def __getitem__(self, key: str) -> Any:
        d = await self._load()
        return d[key]

    async def __setitem__(self, key: Hashable, value: Any) -> None:
        d = await self._load()
        d[key] = value
        await self.r.set_dict(self._key(self.current_step), d)

    async def get(self, key: str, default: Any = None) -> Any:
        d = await self._load()
        return d.get(key, default)

    async def pop(self, key: str, default: Any = None) -> Any:
        d = await self._load()
        value = d.pop(key, default)
        await self.r.set_dict(self._key(self.current_step), d)
        return value

    async def clear(self) -> None:
        self.__data = {}
        await self.r.set_dict(self._key(self.current_step), {})

    async def update(self, other: dict) -> None:
        d = await self._load()
        d.update(other)
        await self.r.set_dict(self._key(self.current_step), d)

    async def keys(self) -> list[str]:
        d = await self._load()
        return list(d.keys())

    async def values(self) -> list[Any]:
        d = await self._load()
        return list(d.values())

    async def items(self) -> list[tuple[str, Any]]:
        d = await self._load()
        return list(d.items())

    async def __contains__(self, key: str) -> bool:
        d = await self._load()
        return key in d

    async def __len__(self) -> int:
        d = await self._load()
        return len(d)
