from typing import Any, Hashable
import json

import pandas as pd

from .redis import RedisClient


class CachedFrameContainer:
    def __init__(self, prefix: str, r: RedisClient):
        self.__tables: dict[str, pd.DataFrame] = dict()
        self.r = r
        self.prefix = prefix

    def __getitem__(self, key: str) -> pd.DataFrame:
        if key not in self.__tables:
            if (table := self.r.get_table(f"{self.prefix}:{key}")) is None:
                raise KeyError(f"Table '{key}' not found in cache.")
            self.__tables[key] = table
            return table
        return self.__tables[key]

    def __setitem__(self, key: str, table: pd.DataFrame) -> None:
        self.__tables[key] = table

    def save(self) -> None:
        for name, table in self.__tables.items():
            self.r.set_table(f"{self.prefix}:{name}", table)

    def clear(self) -> None:
        self.r.delete_pattern(f"{self.prefix}:*")
        self.__tables.clear()

    def copy_from(self, src_prefix: str) -> None:
        """Copy all Redis keys from ``src_prefix`` to this container's prefix.

        Uses Redis ``COPY`` internally — no serialization/deserialization.
        Clears the local in-memory cache so subsequent reads hit Redis.
        """
        if src_prefix == self.prefix:
            return
        self.r.copy_pattern(src_prefix, self.prefix)
        self.__tables.clear()

    def get(self, key: str) -> pd.DataFrame | None:
        if key not in self.__tables:
            table = self.r.get_table(f"{self.prefix}:{key}")
            if table is None:
                return None
            self.__tables[key] = table
        return self.__tables.get(key)

    def keys(self) -> list[str]:
        prefix_len = len(self.prefix) + 1  # +1 for the colon separator
        cached_keys = [
            k[prefix_len:] for k in self.r.get_keys(f"{self.prefix}:*")
        ]
        local_keys = list(self.__tables.keys())
        return list(set(cached_keys + local_keys))

    def items(self) -> list[tuple[str, pd.DataFrame]]:
        """Return (key, DataFrame) pairs from in-memory cache using short keys."""
        return list(self.__tables.items())

    def __repr__(self) -> str:
        return f"CachedFrame(tables={self.keys()})"

    def __str__(self) -> str:
        return self.__repr__()


class CachedDictionary:
    """Caches a single dictionary in memory and persists to Redis on ``save()``."""

    def __init__(self, prefix: str, r: RedisClient):
        self.prefix: str = prefix
        self.r = r
        self.__data: dict | None = None

    @property
    def data(self):
        if self.__data is None:
            self.__data = self.r.get_dict(self.prefix) or {}
        return self.__data

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: Hashable, value: Any) -> None:
        if self.__data is None:
            self.__data = self.r.get_dict(self.prefix) or {}
        self.__data[key] = value

    def save(self) -> None:
        self.r.set_dict(self.prefix, self.data)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def clear(self) -> None:
        self.r.delete(self.prefix)
        self.__data = {}

    def copy_from(self, src_prefix: str) -> None:
        """Copy the Redis key from ``src_prefix`` to this dictionary's prefix.

        Uses Redis ``COPY`` internally — no serialization/deserialization.
        Resets the local cache so the next access re-reads from Redis.
        """
        if src_prefix == self.prefix:
            return
        self.r.copy(src_prefix, self.prefix)
        self.__data = None

    def update(self, other: dict) -> None:
        if self.__data is None:
            self.__data = self.r.get_dict(self.prefix) or {}
        self.__data.update(other)

    def keys(self) -> list[str]:
        if self.__data is None:
            self.__data = self.r.get_dict(self.prefix) or {}
        return list(self.__data.keys())

    def values(self) -> list[Any]:
        if self.__data is None:
            self.__data = self.r.get_dict(self.prefix) or {}
        return list(self.__data.values())

    def items(self) -> list[tuple[str, Any]]:
        if self.__data is None:
            self.__data = self.r.get_dict(self.prefix) or {}
        return list(self.__data.items())

    def __contains__(self, key: str) -> bool:
        if self.__data is None:
            self.__data = self.r.get_dict(self.prefix) or {}
        return key in self.__data

    def __len__(self) -> int:
        return len(self.data)

    def __repr__(self) -> str:
        return f"CachedDictionary({self.data})"

    def __str__(self) -> str:
        return str(self.data)


class StepTracker:
    def __init__(self, prefix: str, r: RedisClient):
        self.prefix = prefix
        self.r = r
        self.__steps: list[str] | None = None

    @property
    def steps(self) -> list[str]:
        if self.__steps is None:
            data = self.r.get(f"{self.prefix}:steps")
            if data is None:
                self.__steps = []
            else:
                self.__steps = json.loads(data.decode("utf-8"))  # type: ignore[no-any-return]
        return self.__steps or []

    def add(self, step_name: str) -> None:
        steps = self.steps
        if step_name in steps:
            return
        steps.append(step_name)
        self.r.set(f"{self.prefix}:steps", json.dumps(steps).encode("utf-8"), ex=self.r.ttl_hours * 3600)
        self.__steps = steps

    def pop(self) -> str | None:
        steps = self.steps
        if not steps:
            return None
        last = steps.pop()
        self.r.set(f"{self.prefix}:steps", json.dumps(steps).encode("utf-8"), ex=self.r.ttl_hours * 3600)
        self.__steps = steps
        return last

    def last(self) -> str | None:
        steps = self.steps
        if not steps:
            return None
        return steps[-1]

    def __repr__(self) -> str:
        return f"StepTracker(steps={self.steps})"