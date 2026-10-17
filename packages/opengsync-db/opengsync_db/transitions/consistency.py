"""Consistency report: records whose status contradicts what their children say.

Only reports; nothing is changed. Each invariant is one SQL query returning the ids of violating
records.

    python -m opengsync_db.transitions.consistency     # uses POSTGRES_* environment variables
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Callable

import sqlalchemy as sa

from ..categories import (
    SeqRequestStatus as RQ, LibraryStatus as LB, ProjectStatus as PJ, ExperimentStatus as EX,
)
from .core import Entity
from . import entities as E

SAMPLE_SIZE = 20


@dataclass(frozen=True)
class Invariant:
    id: str
    entity: Entity
    text: str
    """What should hold for every record."""
    violations: Callable[[], sa.Select]
    """Select of the ids of records that violate it."""
    note: str = ""


@dataclass(frozen=True)
class Finding:
    invariant: Invariant
    count: int
    sample_ids: tuple[int, ...]


def _m():
    from .. import models
    return models


def _request_with_library(*conds: Any) -> sa.ColumnElement[bool]:
    m = _m()
    return sa.exists().where(m.Library.seq_request_id == m.SeqRequest.id, *conds)


def _requests(status: RQ, *conds: Any) -> sa.Select:
    m = _m()
    return sa.select(m.SeqRequest.id).where(m.SeqRequest.status == status, *conds)


def _project_with_library(*conds: Any) -> sa.ColumnElement[bool]:
    m = _m()
    return sa.exists().where(
        m.Sample.project_id == m.Project.id,
        m.links.SampleLibraryLink.sample_id == m.Sample.id,
        m.Library.id == m.links.SampleLibraryLink.library_id,
        *conds,
    )


def _prepared_below_pooled() -> sa.Select:
    m = _m()
    return _requests(RQ.PREPARED, _request_with_library(m.Library.status < LB.POOLED))


def _data_processing_below_sequenced() -> sa.Select:
    m = _m()
    return _requests(RQ.DATA_PROCESSING, _request_with_library(m.Library.status < LB.SEQUENCED))


def _finished_below_shared() -> sa.Select:
    m = _m()
    return _requests(RQ.FINISHED, _request_with_library(m.Library.status < LB.SHARED))


def _shared_but_not_released() -> sa.Select:
    m = _m()
    return _requests(
        RQ.DATA_PROCESSING,
        _request_with_library(m.Library.status == LB.SEQUENCED),
        ~_request_with_library(m.Library.status < LB.SEQUENCED),
        sa.exists().where(
            m.Library.seq_request_id == m.SeqRequest.id,
            m.links.SampleLibraryLink.library_id == m.Library.id,
            m.Sample.id == m.links.SampleLibraryLink.sample_id,
            m.Project.id == m.Sample.project_id,
            m.Project.status == PJ.DELIVERED,
        ),
    )


def _library_in_prep_below_preparing() -> sa.Select:
    m = _m()
    return sa.select(m.Library.id).where(m.Library.lab_prep_id.is_not(None), m.Library.status < LB.PREPARING)


def _experiment_sequenced_without_run() -> sa.Select:
    m = _m()
    return sa.select(m.Experiment.id).where(
        m.Experiment.status.in_([EX.SEQUENCED, EX.DEMULTIPLEXED]),
        ~sa.exists().where(m.SeqRun.experiment_name == m.Experiment.name),
    )


def _delivered_project_with_open_libraries() -> sa.Select:
    m = _m()
    return sa.select(m.Project.id).where(
        m.Project.status == PJ.DELIVERED,
        _project_with_library(m.Library.status.in_([LB.ACCEPTED, LB.PREPARING, LB.STORED, LB.POOLED])),
    )


INVARIANTS: tuple[Invariant, ...] = (
    Invariant("request_prepared_libraries_pooled", E.SEQ_REQUEST, "PREPARED requests have no library below POOLED", _prepared_below_pooled),
    Invariant("request_data_processing_sequenced", E.SEQ_REQUEST, "DATA_PROCESSING requests have no library below SEQUENCED", _data_processing_below_sequenced),
    Invariant("request_finished_shared", E.SEQ_REQUEST, "FINISHED requests have no library below SHARED", _finished_below_shared),
    Invariant(
        "request_shared_not_released", E.SEQ_REQUEST,
        "DATA_PROCESSING requests of a DELIVERED project have no library left at SEQUENCED",
        _shared_but_not_released,
        note="shared through the UI, which did not set libraries to SHARED; they never reach FINISHED",
    ),
    Invariant(
        "library_in_prep_preparing", E.LIBRARY, "libraries in a lab prep are PREPARING or beyond",
        _library_in_prep_below_preparing,
        note="adding libraries to a lab prep stopped setting PREPARING in d9685235 (2026-06-10)",
    ),
    Invariant(
        "experiment_sequenced_has_run", E.EXPERIMENT, "SEQUENCED / DEMULTIPLEXED experiments have a seq run",
        _experiment_sequenced_without_run,
    ),
    Invariant(
        "project_delivered_no_open_libraries", E.PROJECT, "DELIVERED projects have no library with open work",
        _delivered_project_with_open_libraries,
        note="the status worker re-opens these to PROCESSING",
    ),
)


def check(session: Any, invariants: tuple[Invariant, ...] = INVARIANTS) -> list[Finding]:
    findings = []
    for invariant in invariants:
        subquery = invariant.violations().subquery()
        count = session.execute(sa.select(sa.func.count()).select_from(subquery)).scalar_one()
        if count:
            ids = session.execute(sa.select(subquery.c[0]).order_by(subquery.c[0]).limit(SAMPLE_SIZE)).scalars().all()
            findings.append(Finding(invariant, count, tuple(ids)))
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "No inconsistencies found."
    lines = []
    for f in findings:
        more = f" (+{f.count - len(f.sample_ids)} more)" if f.count > len(f.sample_ids) else ""
        lines.append(f"[{f.invariant.id}] {f.count} {f.invariant.entity.label.lower()} records violate: {f.invariant.text}")
        if f.invariant.note:
            lines.append(f"    note: {f.invariant.note}")
        lines.append(f"    ids: {', '.join(map(str, f.sample_ids))}{more}")
    return "\n".join(lines)


def main() -> int:
    from ..core.SyncDBHandler import SyncDBHandler
    db = SyncDBHandler()
    db.connect(
        user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"], port=os.environ.get("POSTGRES_PORT", 5432), db=os.environ["POSTGRES_DB"],
    )
    session = db.open_session()
    try:
        print(format_report(check(session)))
    finally:
        db.close_session(rollback=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
