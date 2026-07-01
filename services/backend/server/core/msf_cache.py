"""Async Redis-backed cache for MultiStepForm state.

Ported from Flask ``tools.RedisMSFFileCache`` to use ``redis.asyncio`` and
integrated with the FastAPI application lifecycle (Redis connection pool
lives on ``app.state.redis_pool``).
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import pandas as pd
import pyarrow as pa
from pyarrow import parquet as pq
from redis.asyncio import Redis

if TYPE_CHECKING:
    from redis.asyncio import ConnectionPool

# Default TTL: 7 days
_DEFAULT_TTL_HOURS = 24 * 7


class MSFCache:
    """Thin async wrapper around Redis for storing step-ordered workflow data.

    Tables are serialised as Parquet via PyArrow; dicts and step lists are
    stored as JSON.  Every key expires after *ttl_hours* hours.
    """

    def __init__(self, pool: ConnectionPool | None = None, ttl_hours: int = _DEFAULT_TTL_HOURS):
        self._pool = pool
        self.ttl_hours = ttl_hours

    def set_pool(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def _pool_or_raise(self) -> ConnectionPool:
        if self._pool is None:
            raise RuntimeError("MSFCache pool has not been initialised – call set_pool() during app lifespan.")
        return self._pool

    # ── Tables (Parquet) ───────────────────────────────────────────

    async def get_table(self, key: str) -> pd.DataFrame | None:
        async with Redis(connection_pool=self._pool_or_raise()) as r:
            data = await r.get(key)
        if data is None:
            return None
        return pd.read_parquet(io.BytesIO(data))  # type: ignore[arg-type]

    async def get_tables(self, pattern: str) -> dict[str, pd.DataFrame]:
        tables: dict[str, pd.DataFrame] = {}
        async with Redis(connection_pool=self._pool_or_raise()) as r:
            async for key in r.scan_iter(match=pattern):
                data = await r.get(key)
                if data is not None:
                    tables[key.decode("utf-8")] = pd.read_parquet(io.BytesIO(data))  # type: ignore[arg-type]
        return tables

    async def set_table(self, key: str, table: pd.DataFrame) -> None:
        buffer = io.BytesIO()
        pq.write_table(pa.Table.from_pandas(table), buffer)
        async with Redis(connection_pool=self._pool_or_raise()) as r:
            await r.set(key, buffer.getvalue(), ex=self.ttl_hours * 3600)

    # ── Dicts (JSON) ───────────────────────────────────────────────

    async def get_dict(self, key: str) -> dict | None:
        async with Redis(connection_pool=self._pool_or_raise()) as r:
            data = await r.get(key)
        if data is None:
            return None
        return json.loads(data.decode("utf-8"))  # type: ignore[no-any-return]

    async def get_dicts(self, pattern: str) -> dict[str, dict]:
        dicts: dict[str, dict] = {}
        async with Redis(connection_pool=self._pool_or_raise()) as r:
            async for key in r.scan_iter(match=pattern):
                data = await r.get(key)
                if data is not None:
                    dicts[key.decode("utf-8")] = json.loads(data.decode("utf-8"))  # type: ignore[no-any-return]
        return dicts

    async def set_dict(self, key: str, data: dict) -> None:
        async with Redis(connection_pool=self._pool_or_raise()) as r:
            await r.set(key, json.dumps(data).encode("utf-8"), ex=self.ttl_hours * 3600)

    # ── Steps (JSON list) ──────────────────────────────────────────

    async def get_steps(self, key: str) -> list[str]:
        async with Redis(connection_pool=self._pool_or_raise()) as r:
            data = await r.get(key)
        if data is None:
            return []
        return json.loads(data.decode("utf-8"))  # type: ignore[no-any-return]

    async def set_steps(self, key: str, steps: list[str]) -> None:
        async with Redis(connection_pool=self._pool_or_raise()) as r:
            await r.set(key, json.dumps(steps).encode("utf-8"), ex=self.ttl_hours * 3600)

    # ── Delete ─────────────────────────────────────────────────────

    async def delete(self, key: str) -> None:
        async with Redis(connection_pool=self._pool_or_raise()) as r:
            await r.delete(key)

    async def delete_pattern(self, pattern: str) -> None:
        async with Redis(connection_pool=self._pool_or_raise()) as r:
            async for key in r.scan_iter(match=pattern):
                await r.delete(key)


# Module-level singleton – configured during app lifespan.
msf_cache = MSFCache()
