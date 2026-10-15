"""Status report of one record: where it is, what comes next, what blocks it, and its history.

Pure data for the Status tab; evaluated against one `Snapshot`, so every child relation is counted
once per report.

The report leads with one *next* block: for requests the current step of their route, for other
records the nearest status ahead. Everything else that could happen now is listed as *other* ways;
ways that don't apply to the current status at all (e.g. unarchive a submitted request) are left out.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import sqlalchemy as sa

from .. import localize
from ..categories import ExtendedEnum, OperationKind
from .core import Entity, Operation, Route, Step
from .registry import Registry, registry
from .relations import Relation
from .rules import Blocker, Snapshot
from .tracking import entity_of, _normalise
from . import entities as E
from . import relations as R
from . import routes as routes_module

StepState = Literal["done", "current", "upcoming", "skipped"]

RELATED: dict[str, tuple[Relation, ...]] = {
    # records counted as related in the history (e.g. a request's libraries)
    E.SEQ_REQUEST.name: (R.REQUEST_SAMPLES, R.REQUEST_LIBRARIES, R.REQUEST_POOLS, R.REQUEST_LAB_PREPS, R.REQUEST_EXPERIMENTS),
    E.PROJECT.name: (R.PROJECT_REQUESTS, R.PROJECT_SAMPLES, R.PROJECT_LIBRARIES),
    E.LAB_PREP.name: (R.PREP_LIBRARIES, R.PREP_POOLS),
    E.EXPERIMENT.name: (R.EXPERIMENT_POOLS, R.EXPERIMENT_LIBRARIES),
    E.POOL.name: (R.POOL_LIBRARIES,),
}

NORMAL_STATUS_LIMIT = 10
"""Status ids from 10 on are side or end states (failed, rejected, archived, …)."""


@dataclass(frozen=True)
class StepReport:
    step: Step
    state: StepState


@dataclass(frozen=True)
class WayReport:
    """One operation that changes this record's status (or completes its current step)."""
    operation: Operation
    destinations: tuple[ExtendedEnum, ...]
    started_here: bool
    """Started from this record's page; its guard was evaluated."""
    available: bool
    blockers: tuple[Blocker, ...] = ()

    @property
    def automatic(self) -> bool:
        return self.operation.kind == OperationKind.WORKER

    @property
    def relevant_blockers(self) -> tuple[Blocker, ...]:
        """Blockers worth showing: about related records (e.g. libraries below POOLED) or conditions
        (e.g. not submittable), not just this record's own status ('status is X, needs Y')."""
        return tuple(b for b in self.blockers if b.kind != "status")

    @property
    def applies(self) -> bool:
        """False when only this record's own status rules it out (it would just say 'status is X, needs Y')."""
        return not self.started_here or self.available or not any(b.kind == "status" for b in self.blockers)


@dataclass(frozen=True)
class HistoryEntry:
    run_id: int
    operation: str
    label: str
    kind: OperationKind
    actor_id: int | None
    comment: str | None
    reason: str | None
    inferred: bool
    timestamp: datetime
    own_change: tuple[int | None, int | None] | None
    """(from, to) status ids of this record in the run, if it changed."""
    related_changes: dict[tuple[str, int | None, int | None], int]
    """(entity type, from, to) → count, for changes of records related to this one (its libraries, …)."""


@dataclass
class StatusReport:
    entity: Entity
    obj: Any
    status: ExtendedEnum | None
    route: Route | None = None
    route_inferred: bool = True
    steps: list[StepReport] = field(default_factory=list)
    next_title: str | None = None
    next_ways: list[WayReport] = field(default_factory=list)
    next_blockers: list[Blocker] = field(default_factory=list)
    other_ways: list[WayReport] = field(default_factory=list)
    queries: int = 0

    @property
    def current_step(self) -> StepReport | None:
        return next((s for s in self.steps if s.state == "current"), None)


def _steps(snapshot: Snapshot, route: Route, obj: Any) -> tuple[list[StepReport], list[Blocker]]:
    done = [step.done_when.evaluate(snapshot, obj) for step in route.steps]
    last_done = max((i for i, verdict in enumerate(done) if verdict.holds), default=-1)
    reports: list[StepReport] = []
    blockers: list[Blocker] = []
    current_set = False
    for i, (step, verdict) in enumerate(zip(route.steps, done)):
        if verdict.holds:
            reports.append(StepReport(step, "done"))
        elif step.optional and i < last_done:
            reports.append(StepReport(step, "skipped"))
        elif not current_set and not step.optional:
            reports.append(StepReport(step, "current"))
            blockers = list(verdict.blockers)
            current_set = True
        else:
            reports.append(StepReport(step, "upcoming"))
    return reports, blockers


def _way(snapshot: Snapshot, entity: Entity, obj: Any, op: Operation, destinations: tuple) -> WayReport:
    if op.subject != entity:
        return WayReport(op, destinations, False, False)
    verdict = op.guard.evaluate(snapshot, obj) if op.guard is not None else None
    return WayReport(op, destinations, True, verdict is None or verdict.holds, verdict.blockers if verdict is not None else ())


def _outgoing_ways(reg: Registry, snapshot: Snapshot, entity: Entity, obj: Any, status: ExtendedEnum | None) -> dict[str, WayReport]:
    destinations: dict[Operation, list] = defaultdict(list)
    for dst, ops in reg.outgoing(entity, status).items():
        for op in ops:
            destinations[op].append(dst)
    return {
        op.id: _way(snapshot, entity, obj, op, tuple(sorted(dsts, key=lambda s: s.id)))
        for op, dsts in destinations.items()
    }


def _dedupe(blockers: list[Blocker]) -> list[Blocker]:
    seen: set[str] = set()
    out = []
    for b in blockers:
        if b.kind != "status" and b.text not in seen:
            seen.add(b.text)
            out.append(b)
    return out


def _sort_ways(ways: list[WayReport]) -> list[WayReport]:
    return sorted(ways, key=lambda w: (not (w.started_here and w.available), w.automatic, not w.started_here, w.operation.label))


def build(session: Any, obj: Any, reg: Registry | None = None) -> StatusReport:
    reg = reg or registry()
    entity = entity_of(obj)
    if entity is None:
        raise ValueError(f"{type(obj).__name__} has no tracked status")
    snapshot = Snapshot(session)
    # a record created in this session may still hold its column default as a plain int
    status = _normalise(entity, getattr(obj, entity.attr))
    report = StatusReport(entity=entity, obj=obj, status=status)
    ways = _outgoing_ways(reg, snapshot, entity, obj, status)

    primary: list[WayReport] = []
    blockers: list[Blocker] = []
    if entity == E.SEQ_REQUEST:
        report.route = routes_module.infer_route(session, obj)
        report.route_inferred = getattr(obj, "route_override", None) not in routes_module.BY_ID
        report.steps, blockers = _steps(snapshot, report.route, obj)
        if (current := report.current_step) is not None:
            report.next_title = current.step.label
            for op_id in current.step.alternatives:
                if (op := reg.operations.get(op_id)) is not None:
                    primary.append(ways.get(op_id) or _way(snapshot, entity, obj, op, ()))
    else:
        ahead = sorted(
            {dst for way in ways.values() for dst in way.destinations
             if dst.id < NORMAL_STATUS_LIMIT and (status is None or dst.id > status.id)},
            key=lambda s: s.id,
        )
        if ahead:
            report.next_title = ahead[0].display_name
            primary = [way for way in ways.values() if ahead[0] in way.destinations]

    applicable = [w for w in primary if w.applies]
    report.next_ways = _sort_ways(applicable or primary)
    report.next_blockers = _dedupe(blockers + [b for w in report.next_ways for b in w.relevant_blockers])
    primary_ids = {w.operation.id for w in primary}
    report.other_ways = _sort_ways([w for op_id, w in ways.items() if op_id not in primary_ids and w.applies])
    report.queries = snapshot.queries
    return report


def _related_ids(session: Any, entity: Entity, obj: Any, candidates: dict[str, set[int]]) -> dict[str, set[int]]:
    """Which of the candidate (entity type → ids) are related to this record."""
    related: dict[str, set[int]] = defaultdict(set)
    for relation in RELATED.get(entity.name, ()):
        ids = candidates.get(relation.child.name)
        if not ids:
            continue
        model = relation.child.model
        id_col = getattr(model, relation.child.id_attr)
        related[relation.child.name].update(session.execute(
            sa.select(id_col).where(relation.where(obj), id_col.in_(ids))
        ).scalars())
    return related


def history(session: Any, obj: Any, limit: int = 100, reg: Registry | None = None) -> list[HistoryEntry]:
    """Runs that changed this record or were started from it, newest first.

    Changes of other records are only counted when they are related to this one (e.g. the libraries
    of a request) and never for migrations, which touch every record."""
    from .. import models
    reg = reg or registry()
    entity = entity_of(obj)
    if entity is None:
        raise ValueError(f"{type(obj).__name__} has no tracked status")
    entity_id = getattr(obj, entity.id_attr)
    key = getattr(obj, entity.key_attr) if entity.key_attr else None
    SC, OR = models.StatusChange, models.OperationRun

    own = sa.and_(SC.entity_type == entity.name, SC.entity_id == entity_id)
    if entity.key_attr:
        own = sa.and_(own, SC.entity_key == key)
    run_ids = sa.union(
        sa.select(SC.run_id).where(own),
        sa.select(OR.id).where(OR.subject_type == entity.name, OR.subject_id == entity_id),
    ).subquery()
    runs = session.execute(
        sa.select(OR).where(OR.id.in_(sa.select(run_ids.c[0]))).order_by(OR.timestamp_utc.desc(), OR.id.desc()).limit(limit)
    ).scalars().all()
    if not runs:
        return []

    runs_with_others = [run.id for run in runs if run.kind != OperationKind.MIGRATION]
    own_rows = session.execute(
        sa.select(SC.run_id, SC.from_status, SC.to_status, SC.inferred, SC.timestamp_utc)
        .where(SC.run_id.in_([run.id for run in runs]), own)
    ).all()
    other_rows = session.execute(
        sa.select(SC.run_id, SC.entity_type, SC.entity_id, SC.from_status, SC.to_status)
        .where(SC.run_id.in_(runs_with_others), sa.not_(own))
    ).all() if runs_with_others else []

    own_changes = {row.run_id: (row.from_status, row.to_status) for row in own_rows}
    inferred = {row.run_id: row.inferred for row in own_rows}
    own_timestamps = {row.run_id: row.timestamp_utc for row in own_rows}

    candidates: dict[str, set[int]] = defaultdict(set)
    for row in other_rows:
        candidates[row.entity_type].add(row.entity_id)
    related = _related_ids(session, entity, obj, candidates)
    related_changes: dict[int, dict] = defaultdict(lambda: defaultdict(int))
    for row in other_rows:
        if row.entity_id in related.get(row.entity_type, ()):
            related_changes[row.run_id][(row.entity_type, row.from_status, row.to_status)] += 1

    entries = []
    for run in runs:
        op = reg.operations.get(run.operation)
        is_inferred = run.inferred or inferred.get(run.id, False)
        entries.append(HistoryEntry(
            run_id=run.id, operation=run.operation, label=op.label if op else run.operation, kind=run.kind,
            actor_id=run.actor_id, comment=run.comment, reason=run.reason, inferred=is_inferred,
            # inferred changes carry their original time; the run only has the migration time
            timestamp=localize(own_timestamps[run.id]) if is_inferred and run.id in own_timestamps else run.timestamp,
            own_change=own_changes.get(run.id), related_changes=dict(related_changes[run.id]),
        ))
    entries.sort(key=lambda e: (e.timestamp, e.run_id), reverse=True)
    return entries
