"""Run folder scanner: status changes are recorded with the run folder as reason."""
from pathlib import Path

import pytest
import sqlalchemy as sa

from opengsync_db import SyncDBHandler, models
from opengsync_db.categories import ExperimentWorkFlow, ExperimentStatus, RunStatus, OperationKind, ReadType

from ..db.create_units import create_user, create_experiment, create_seq_run


@pytest.fixture
def scanner(import_worker_task, monkeypatch: pytest.MonkeyPatch):
    module = import_worker_task("rf_scanner")
    monkeypatch.setattr(module, "parse_metrics", lambda run_folder: {})
    return module


def _fake_parse(monkeypatch: pytest.MonkeyPatch, module, experiment_name: str) -> None:
    monkeypatch.setattr(module, "parse_run_folder", lambda run_folder: {
        "started": None, "experiment_name": experiment_name, "r1_cycles": 1, "i1_cycles": 1, "i2_cycles": 1, "r2_cycles": 1,
        "flowcell_id": "FC1", "instrument": "NovaSeq", "rta_version": "4", "run_id": "RUN1", "read_type": ReadType.PAIRED_END,
    })


def _run_folder(root: Path, name: str, complete: bool) -> Path:
    folder = root / name
    folder.mkdir()
    (folder / "RunParameters.xml").write_text("<RunParameters/>")
    if complete:
        (folder / "RTAComplete.txt").write_text("")
    return folder


def _runs(session, operation: str) -> list[models.OperationRun]:
    return list(session.execute(sa.select(models.OperationRun).where(models.OperationRun.operation == operation)).scalars())


def _experiment_with_run(session, run_status: RunStatus, run_folder: str):
    experiment = create_experiment(session, create_user(session), ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    run = create_seq_run(session)
    run.experiment_name = experiment.name
    run.run_folder = run_folder
    run.status = run_status
    session.save(run, flush=True)
    session.commit()
    return experiment, run


def test_removed_folder_archives_run(_db_handler: SyncDBHandler, scanner, tmp_path: Path):
    session = _db_handler.session
    experiment, run = _experiment_with_run(session, RunStatus.RUNNING, "gone")

    _db_handler.session.info["transitions.mode"] = "strict"  # the worker declares every change
    scanner.process_run_folder(tmp_path, _db_handler)
    session.commit()

    assert run.status == RunStatus.ARCHIVED and experiment.status == ExperimentStatus.ARCHIVED
    [op] = _runs(session, "worker.rf_folder_missing")
    assert op.kind == OperationKind.WORKER and op.actor_id is None
    assert op.reason == f"run folder {tmp_path / 'gone'} no longer exists"
    assert {(c.entity_type, c.to_status) for c in op.changes} == {
        ("seq_run", RunStatus.ARCHIVED.id), ("experiment", ExperimentStatus.ARCHIVED.id),
    }


def test_new_finished_run(_db_handler: SyncDBHandler, scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    session = _db_handler.session
    experiment = create_experiment(session, create_user(session), ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    session.commit()
    folder = _run_folder(tmp_path, "run_1", complete=True)
    _fake_parse(monkeypatch, scanner, experiment.name)

    _db_handler.session.info["transitions.mode"] = "strict"  # the worker declares every change
    scanner.process_run_folder(tmp_path, _db_handler)
    session.commit()

    session.refresh(experiment)
    # legacy: the new run's experiment is not loaded yet, so it only cascades on the next scan
    assert experiment.status == ExperimentStatus.DRAFT
    [op] = _runs(session, "worker.rf_new_run")
    assert op.reason == f"new run folder {folder} detected (RTAComplete.txt found)"
    assert [(c.entity_type, c.from_status, c.to_status, c.declared) for c in op.changes] == [
        ("seq_run", None, RunStatus.FINISHED.id, True),
    ]

    _db_handler.session.info["transitions.mode"] = "strict"  # the worker declares every change
    scanner.process_run_folder(tmp_path, _db_handler)
    session.commit()
    session.refresh(experiment)
    assert experiment.status == ExperimentStatus.SEQUENCED
    [cascade] = _runs(session, "worker.rf_run_finished")
    assert cascade.reason == f"run {folder.name} is FINISHED (RTAComplete.txt found in {folder})"


def test_running_run_finishes(_db_handler: SyncDBHandler, scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    session = _db_handler.session
    experiment, run = _experiment_with_run(session, RunStatus.RUNNING, "run_2")
    folder = _run_folder(tmp_path, "run_2", complete=True)
    _fake_parse(monkeypatch, scanner, experiment.name)

    _db_handler.session.info["transitions.mode"] = "strict"  # the worker declares every change
    scanner.process_run_folder(tmp_path, _db_handler)
    session.commit()

    assert run.status == RunStatus.FINISHED
    [op] = _runs(session, "worker.rf_run_status")
    assert op.reason == f"status read from run folder {folder} (RTAComplete.txt found)"


def test_folder_back(_db_handler: SyncDBHandler, scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    session = _db_handler.session
    experiment, run = _experiment_with_run(session, RunStatus.ARCHIVED, "run_3")
    folder = _run_folder(tmp_path, "run_3", complete=True)
    _fake_parse(monkeypatch, scanner, experiment.name)

    _db_handler.session.info["transitions.mode"] = "strict"  # the worker declares every change
    scanner.process_run_folder(tmp_path, _db_handler)
    session.commit()

    assert run.status == RunStatus.FINISHED
    [op] = _runs(session, "worker.rf_folder_back")
    assert op.reason == f"run folder {folder} reappeared"


def test_rescan_writes_nothing(_db_handler: SyncDBHandler, scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    session = _db_handler.session
    experiment = create_experiment(session, create_user(session), ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    session.commit()
    _run_folder(tmp_path, "run_4", complete=True)
    _fake_parse(monkeypatch, scanner, experiment.name)

    for _ in range(2):  # the second scan cascades to the experiment
        _db_handler.session.info["transitions.mode"] = "strict"  # the worker declares every change
        scanner.process_run_folder(tmp_path, _db_handler)
        session.commit()
    before = session.execute(sa.select(sa.func.count()).select_from(models.StatusChange)).scalar_one()
    _db_handler.session.info["transitions.mode"] = "strict"  # the worker declares every change
    scanner.process_run_folder(tmp_path, _db_handler)
    session.commit()
    assert session.execute(sa.select(sa.func.count()).select_from(models.StatusChange)).scalar_one() == before
