import io
import json

import pandas as pd
import pyarrow as pa
from pyarrow import parquet as pq
from redis import Redis, ConnectionPool


# Default TTL: 7 days
_DEFAULT_TTL_HOURS = 24 * 7


class RedisClient(Redis):
    def __init__(self, pool: ConnectionPool, ttl_hours: int = _DEFAULT_TTL_HOURS):
        super().__init__(connection_pool=pool)
        self.ttl_hours = ttl_hours

    def get_table(self, key: str) -> pd.DataFrame | None:
        if (data := self.get(key)) is None:  # type: ignore[assignment]
            return None
        return pd.read_parquet(io.BytesIO(data))  # type: ignore[arg-type]

    def get_tables(self, pattern: str) -> dict[str, pd.DataFrame]:
        tables: dict[str, pd.DataFrame] = {}
        for key in self.scan_iter(match=pattern):
            data = self.get(key)
            if data is not None:
                tables[key.decode("utf-8")] = pd.read_parquet(io.BytesIO(data))  # type: ignore[arg-type]
        return tables

    def set_table(self, key: str, table: pd.DataFrame) -> None:
        buffer = io.BytesIO()
        pq.write_table(pa.Table.from_pandas(table), buffer)
        self.set(key, buffer.getvalue(), ex=self.ttl_hours * 3600)

    # ── Dicts (JSON) ───────────────────────────────────────────────

    def get_dict(self, key: str) -> dict | None:
        if (data := self.get(key)) is None:
            return None
        return json.loads(data.decode("utf-8"))  # type: ignore[no-any-return]

    def get_dicts(self, pattern: str) -> dict[str, dict]:
        dicts: dict[str, dict] = {}
        for key in self.scan_iter(match=pattern):
            data = self.get(key)
            if data is not None:
                dicts[key.decode("utf-8")] = json.loads(data.decode("utf-8"))  # type: ignore[no-any-return]
        return dicts

    def set_dict(self, key: str, data: dict) -> None:
        self.set(key, json.dumps(data).encode("utf-8"), ex=self.ttl_hours * 3600)

    def delete(self, key: str) -> None:
        self.delete(key)

    def delete_pattern(self, pattern: str) -> None:
        for key in self.scan_iter(match=pattern):
            self.delete(key)
