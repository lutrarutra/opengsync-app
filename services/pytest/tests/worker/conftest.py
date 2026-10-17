import sys
import types
import logging
import importlib
import importlib.util
from typing import Callable

import pytest


@pytest.fixture  # type: ignore[attr-defined]
def import_worker_task(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], types.ModuleType]:
    """Imports a module of opengsync_worker.tasks without running the worker package __init__ files,
    which read /app/opengsync.yaml and set up celery."""
    spec = importlib.util.find_spec("opengsync_worker")
    assert spec is not None and spec.submodule_search_locations is not None
    pkg_dir = list(spec.submodule_search_locations)[0]

    worker = types.ModuleType("opengsync_worker")
    worker.__path__ = [pkg_dir]
    tasks = types.ModuleType("opengsync_worker.tasks")
    tasks.__path__ = [f"{pkg_dir}/tasks"]
    tasks.logger = logging.getLogger("opengsync_worker.tasks")  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "opengsync_worker", worker)
    monkeypatch.setitem(sys.modules, "opengsync_worker.tasks", tasks)

    def _import(name: str) -> types.ModuleType:
        monkeypatch.delitem(sys.modules, f"opengsync_worker.tasks.{name}", raising=False)
        return importlib.import_module(f"opengsync_worker.tasks.{name}")

    return _import
