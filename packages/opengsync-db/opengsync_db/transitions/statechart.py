"""State chart of one record: its entity's statuses as cards and the actions between them as edges.

The chart is the entity's state graph from the registry (actions, workflows, API calls and worker
rules; not manual edits), with the record on top: its current status, the statuses and transitions
it went through (from its status history), and for the edges leaving the current status whether
they are possible now, blocked (and why), automatic, or done from another page.

Actions that don't check the source status ("from any status") start where their guard allows them
(e.g. accept: from SUBMITTED); without such a guard (e.g. archive) they are only drawn from the
current status, otherwise they would connect every card. Unchecked side effects of actions on other
records (e.g. completing a lab prep sets the request PREPARED) are only drawn from the current status
when they are one of the ways to its next step.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from ..categories import ExtendedEnum
from .core import ANY, Entity, Operation, spec_str
from .registry import Registry, registry
from .rules import All, Rule, StatusIn
from .status import NORMAL_STATUS_LIMIT, HistoryEntry, StatusReport, WayReport

BASELINE = "migration.baseline"
"""Its changes say what the status was at the migration, not when it was set."""

EdgeState = Literal["available", "blocked", "automatic", "elsewhere", "inactive"]


@dataclass
class Card:
    status: ExtendedEnum
    current: bool = False
    visited: bool = False
    since: datetime | None = None

    @property
    def side(self) -> bool:
        return self.status.id >= NORMAL_STATUS_LIMIT


@dataclass
class Action:
    operation: Operation
    state: EdgeState = "inactive"
    blockers: tuple[str, ...] = ()
    other_effects: tuple[str, ...] = ()


@dataclass
class Transition:
    source: ExtendedEnum
    target: ExtendedEnum
    actions: list[Action] = field(default_factory=list)
    taken: bool = False
    from_current: bool = False

    @property
    def state(self) -> EdgeState:
        """Best state among the actions (only edges leaving the current status have one)."""
        for state in ("available", "automatic", "blocked", "elsewhere"):
            if any(a.state == state for a in self.actions):
                return state  # type: ignore[return-value]
        return "inactive"


@dataclass
class StateChart:
    entity: Entity
    cards: list[Card]
    transitions: list[Transition]


def _other_effects(entity: Entity, op: Operation) -> tuple[str, ...]:
    out = []
    for effect in op.effects:
        if effect.entity == entity:
            continue
        dst = "chosen status" if effect.dst is ANY else spec_str(effect.dst)
        text = f"{effect.entity.label_plural}: {spec_str(effect.src)} → {dst}"
        if effect.when:
            text += f" ({effect.when})"
        out.append(text)
    return tuple(out)


def _guard_statuses(op: Operation, entity: Entity) -> frozenset | None:
    """Statuses the operation's guard requires of the record itself, if it has such a condition."""
    if op.subject != entity or op.guard is None:
        return None

    def find(rule: Rule) -> frozenset | None:
        if isinstance(rule, StatusIn) and rule.attr == entity.attr:
            return rule.allowed
        if isinstance(rule, All):
            for child in rule.rules:
                if (found := find(child)) is not None:
                    return found
        return None

    return find(op.guard)


def _action_state(way: WayReport | None) -> tuple[EdgeState, tuple[str, ...]]:
    if way is None:
        return "inactive", ()
    if way.automatic:
        return ("automatic" if way.available or not way.started_here else "blocked"), tuple(b.text for b in way.relevant_blockers)
    if not way.started_here:
        return "elsewhere", ()
    if way.available:
        return "available", ()
    return "blocked", tuple(b.text for b in way.relevant_blockers)


def build(report: StatusReport, history: list[HistoryEntry], reg: Registry | None = None) -> StateChart:
    """Chart for the record of `report`; `history` is its status history (newest first)."""
    reg = reg or registry()
    entity = report.entity
    current = report.status
    ways: dict[str, WayReport] = {w.operation.id: w for w in report.next_ways + report.other_ways}
    next_ids = {w.operation.id for w in report.next_ways}

    taken: set[tuple[int | None, int | None]] = set()
    visited: set[int] = set()
    since: datetime | None = None
    for entry in history:
        if entry.own_change is None:
            continue
        src, dst = entry.own_change
        taken.add((src, dst))
        if dst is not None:
            visited.add(dst)
        if since is None and current is not None and dst == current.id and entry.operation != BASELINE:
            since = entry.timestamp  # newest entry that set the current status

    transitions: dict[tuple[ExtendedEnum, ExtendedEnum], Transition] = {}
    for edge in reg.edges(entity):
        if edge.src is None:
            continue  # creation
        if edge.effect.src is ANY and edge.effect.via == "self":
            intended = _guard_statuses(edge.operation, entity)
            if (intended is None and edge.src != current) or (intended is not None and edge.src not in intended):
                continue
        elif edge.effect.src is ANY and (edge.src != current or edge.operation.id not in next_ids):
            # a side effect from another record without a status check (e.g. completing a lab prep sets
            # the request PREPARED): only drawn when it is how this record gets to its next step
            continue
        key = (edge.src, edge.dst)
        transition = transitions.setdefault(key, Transition(edge.src, edge.dst))
        if any(a.operation == edge.operation for a in transition.actions):
            continue
        state, blockers = ("inactive", ())
        if edge.src == current:
            state, blockers = _action_state(ways.get(edge.operation.id))
        transition.actions.append(Action(edge.operation, state, blockers, _other_effects(entity, edge.operation)))

    for (src, dst), transition in transitions.items():
        transition.taken = (src.id, dst.id) in taken
        transition.from_current = src == current

    connected = {s for key in transitions for s in key}
    cards = [
        Card(status, current=status == current, visited=status.id in visited, since=since if status == current else None)
        for status in entity.status_enum
        if status in connected or status == current or status.id in visited
    ]
    order = defaultdict(int, {"available": 0, "automatic": 1, "blocked": 2, "elsewhere": 3, "inactive": 4})
    for transition in transitions.values():
        transition.actions.sort(key=lambda a: (order[a.state], a.operation.label))
    return StateChart(entity, cards, list(transitions.values()))
