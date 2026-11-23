"""A thread limit of its own for share-link and WebDAV requests (docs/file-share.md#load-and-throttling).

Sync FastAPI routes run in anyio's default threadpool (40 threads per worker), which every other page shares.
A share download checks the file on the share mount first, a round trip per stat on sshfs, and rclone keeps
up to 24 requests per client in flight, so a few large downloads could take every thread and make the rest
of the app wait. Share routes are `async def` and hand their work to `run`: at most `share_threads` of them
use threads at a time, and the others wait as coroutines, which hold no thread.
"""
import asyncio
import functools
import weakref
from collections.abc import Callable
from typing import Any, TypeVar

import anyio
import anyio.to_thread

from ..core import config

DEFAULT_THREADS = 16
T = TypeVar("T")

# one limiter per event loop: an anyio limiter belongs to the loop it was first used in (tests start several)
_limiters: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, anyio.CapacityLimiter]" = weakref.WeakKeyDictionary()


def _threads() -> int:
    try:
        return max(1, int(config.settings.app_config.share_threads))
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return DEFAULT_THREADS


def limiter() -> anyio.CapacityLimiter:
    loop = asyncio.get_running_loop()
    if (current := _limiters.get(loop)) is None:
        current = _limiters[loop] = anyio.CapacityLimiter(_threads())
    return current


async def run(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """`fn(*args, **kwargs)` in a worker thread, at most `share_threads` at a time per app worker."""
    return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs), limiter=limiter())
