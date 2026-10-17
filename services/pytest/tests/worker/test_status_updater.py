import sys
import types
import logging
import importlib
import importlib.util

import pytest

from opengsync_db import SyncDBHandler
from opengsync_db.categories import ExperimentWorkFlow, ExperimentStatus, RunStatus

from ..db.create_units import create_user, create_experiment, create_seq_run


@pytest.fixture  # type: ignore[attr-defined]
def update_statuses(monkeypatch: pytest.MonkeyPatch):
    """Imports the status updater without running the worker package __init__ files,
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
    monkeypatch.delitem(sys.modules, "opengsync_worker.tasks.status_updater", raising=False)

    return importlib.import_module("opengsync_worker.tasks.status_updater").update_statuses


@pytest.mark.parametrize("run_status, expected", [  # type: ignore[attr-defined]
    (None, ExperimentStatus.DRAFT),
    (RunStatus.RUNNING, ExperimentStatus.SEQUENCING),
    (RunStatus.FINISHED, ExperimentStatus.SEQUENCED),
    (RunStatus.ARCHIVED, ExperimentStatus.ARCHIVED),
])
def test_experiment_status_follows_seq_run(
    _db_handler: SyncDBHandler, update_statuses, run_status: RunStatus | None, expected: ExperimentStatus
):
    session = _db_handler.session
    user = create_user(session)
    experiment = create_experiment(session, user, ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    assert experiment.status == ExperimentStatus.DRAFT

    if run_status is not None:
        run = create_seq_run(session)
        run.experiment_name = experiment.name
        run.status = run_status
        session.save(run, flush=True)

    _db_handler.session.info["transitions.mode"] = "strict"  # the worker declares every change
    update_statuses(_db_handler)

    session.refresh(experiment)
    # Legacy only promoted experiments with a FINISHED/ARCHIVED run; one without a run stays DRAFT.
    assert experiment.status == expected


def test_rules_are_recorded_as_worker_runs(_db_handler: SyncDBHandler, update_statuses):
    import sqlalchemy as sa
    from opengsync_db import models
    from opengsync_db.categories import OperationKind

    session = _db_handler.session
    user = create_user(session)
    experiment = create_experiment(session, user, ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    run = create_seq_run(session)
    run.experiment_name = experiment.name
    session.save(run, flush=True)
    session.commit()

    _db_handler.session.info["transitions.mode"] = "strict"  # the worker declares every change
    update_statuses(_db_handler)
    session.commit()

    [op] = session.execute(
        sa.select(models.OperationRun).where(models.OperationRun.operation == "worker.experiment_sequencing")
    ).scalars().all()
    assert op.kind == OperationKind.WORKER and op.actor_id is None
    assert op.reason == "seq run of the experiment is RUNNING"
    [change] = op.changes
    assert (change.entity_id, change.to_status, change.declared) == (experiment.id, ExperimentStatus.SEQUENCING.id, True)
    assert change.detail == f"seq run {run.run_folder}"

    count = session.execute(sa.select(sa.func.count()).select_from(models.OperationRun)).scalar_one()
    _db_handler.session.info["transitions.mode"] = "strict"  # the worker declares every change
    update_statuses(_db_handler)
    session.commit()
    # nothing changed, so no new runs (they are created on the first change only)
    assert session.execute(sa.select(sa.func.count()).select_from(models.OperationRun)).scalar_one() == count
