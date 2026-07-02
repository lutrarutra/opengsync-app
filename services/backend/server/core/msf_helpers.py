import json
from typing import Any, Hashable

import pandas as pd

from .redis import RedisClient


class MSFTableHandler:
    def __init__(self, template: str, r: RedisClient, steps: list[str]):
        self.__tables: dict[str, pd.DataFrame] = {}
        self.template = template
        self.r = r
        self._steps_reversed = list(reversed(steps))  # oldest → newest
        self.current_step = steps[-1] if steps else ""

    def _key(self, step_name: str, table_name: str) -> str:
        return self.template.format(step=step_name, table=table_name)

    def __getitem__(self, key: str) -> pd.DataFrame:
        if key in self.__tables:
            return self.__tables[key]

        for step in self._steps_reversed:
            table = self.r.get_table(self._key(step, key))
            if table is not None:
                self.__tables[key] = table
                return table

        raise KeyError(f"Table '{key}' not found in any step.")

    def __setitem__(self, key: str, table: pd.DataFrame) -> None:
        self.__tables[key] = table
        self.r.set_table(self._key(self.current_step, key), table)

    def get(self, key: str, step: str | None = None) -> pd.DataFrame | None:
        if step is not None:
            return self.r.get_table(self._key(step, key))
        try:
            return self[key]
        except KeyError:
            return None

    def set_steps(self, key: str, steps: list[str]) -> None:
        self.r.set(key, json.dumps(steps).encode("utf-8"), ex=self.r.ttl_hours * 3600)

    def keys(self) -> list[str]:
        tables = list(self.__tables.keys())
        for step in self._steps_reversed:
            pattern = self.template.format(step=step, table="*")
            for raw_key in self.r.scan_iter(match=pattern):
                table_name = raw_key.decode("utf-8").split(":")[-1]
                if table_name not in tables:
                    tables.append(table_name)
        return tables

class CachedDictionary:

    def __init__(self, template: str, r: RedisClient, steps: list[str]):
        self.__data: dict | None = None
        self.template = template
        self.r = r
        self._steps_reversed = list(reversed(steps))
        self.current_step = steps[0] if steps else ""

    def _key(self, step_name: str) -> str:
        return self.template.format(step=step_name)

    def _load(self) -> dict:
        if self.__data is None:
            for step in self._steps_reversed:
                d = self.r.get_dict(self._key(step))
                if d is not None:
                    self.__data = d
                    break
            else:
                self.__data = {}
        return self.__data

    def __getitem__(self, key: str) -> Any:
        d = self._load()
        return d[key]

    def __setitem__(self, key: Hashable, value: Any) -> None:
        d = self._load()
        d[key] = value
        self.r.set_dict(self._key(self.current_step), d)

    def get(self, key: str, default: Any = None) -> Any:
        d = self._load()
        return d.get(key, default)

    def pop(self, key: str, default: Any = None) -> Any:
        d = self._load()
        value = d.pop(key, default)
        self.r.set_dict(self._key(self.current_step), d)
        return value

    def clear(self) -> None:
        self.__data = {}
        self.r.set_dict(self._key(self.current_step), {})

    def update(self, other: dict) -> None:
        d = self._load()
        d.update(other)
        self.r.set_dict(self._key(self.current_step), d)

    def keys(self) -> list[str]:
        d = self._load()
        return list(d.keys())

    def values(self) -> list[Any]:
        d = self._load()
        return list(d.values())

    def items(self) -> list[tuple[str, Any]]:
        d = self._load()
        return list(d.items())

    def __contains__(self, key: str) -> bool:
        d = self._load()
        return key in d

    def __len__(self) -> int:
        d = self._load()
        return len(d)
