"""Rules: named preconditions that can explain why they do not hold.

A rule is evaluated against a `Snapshot`, which caches one `GROUP BY status` query per child
relation, so evaluating many rules for one object costs one query per relation, not per rule.
Statuses are compared by membership in explicit sets built with `below()` / `at_least()`, which
reproduces the legacy id comparisons (ids >= 10 count as "done").
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import sqlalchemy as sa

from ..categories import ExtendedEnum
from .core import spec_str
from .relations import Relation

BLOCKER_SAMPLE_SIZE = 10


@dataclass(frozen=True)
class Blocker:
    text: str
    relation: Relation | None = None
    statuses: frozenset = frozenset()
    count: int = 0
    sample_ids: tuple[int, ...] = ()
    kind: str = "condition"
    """'status' when it is only about the record's own status ('status is X, needs Y')."""
    of: int = 0
    """Children counted by the rule (for a progress bar: `of - count` of `of` are fine), 0 if not a count."""
    breakdown: str = ""
    """The blocking children per status, e.g. '3 ACCEPTED, 2 POOLED'."""

    @property
    def done(self) -> int:
        return self.of - self.count


@dataclass(frozen=True)
class Verdict:
    holds: bool
    blockers: tuple[Blocker, ...] = ()

    def __bool__(self) -> bool:
        return self.holds


HOLDS = Verdict(True)


class Snapshot:
    """Per-object cache of child status counts."""

    def __init__(self, session: Any) -> None:
        self.session = session
        self._counts: dict[tuple[str, str, Any], dict[Any, int]] = {}
        self.queries = 0

    def _key(self, relation: Relation, obj: Any) -> tuple[str, str, Any]:
        return (relation.parent.name, relation.name, getattr(obj, relation.parent.id_attr))

    def counts(self, relation: Relation, obj: Any) -> dict[Any, int]:
        key = self._key(relation, obj)
        if key not in self._counts:
            model = relation.child.model
            col = getattr(model, relation.child.attr)
            stmt = sa.select(col, sa.func.count()).where(relation.where(obj)).group_by(col)
            self.queries += 1
            self._counts[key] = {status: n for status, n in self.session.execute(stmt).all()}
        return self._counts[key]

    def sample_ids(self, relation: Relation, obj: Any, statuses: Iterable[Any], limit: int = BLOCKER_SAMPLE_SIZE) -> tuple[int, ...]:
        model = relation.child.model
        col = getattr(model, relation.child.attr)
        statuses = list(statuses)
        cond = col.in_([s for s in statuses if s is not None])
        if None in statuses:
            cond = sa.or_(cond, col.is_(None))
        id_col = getattr(model, relation.child.id_attr)
        stmt = sa.select(id_col).where(relation.where(obj), cond).order_by(id_col).limit(limit)
        self.queries += 1
        return tuple(self.session.execute(stmt).scalars().all())


class Rule(ABC):
    @abstractmethod
    def describe(self) -> str: ...

    @abstractmethod
    def evaluate(self, snapshot: Snapshot, obj: Any) -> Verdict: ...

    def __and__(self, other: "Rule") -> "Rule":
        return All(self, other)

    def __or__(self, other: "Rule") -> "Rule":
        return AnyOf(self, other)

    def __invert__(self) -> "Rule":
        return Not(self)

    def __str__(self) -> str:
        return self.describe()


@dataclass(frozen=True)
class StatusIn(Rule):
    """The object's own status is in the set."""
    allowed: frozenset
    attr: str = "status"

    def describe(self) -> str:
        return f"status is {spec_str(self.allowed)}"

    def evaluate(self, snapshot: Snapshot, obj: Any) -> Verdict:
        status = getattr(obj, self.attr)
        if status in self.allowed:
            return HOLDS
        label = status.name if isinstance(status, ExtendedEnum) else str(status)
        return Verdict(False, (Blocker(f"status is {label}, needs {spec_str(self.allowed)}", kind="status"),))


@dataclass(frozen=True)
class AttrIn(Rule):
    """An enum attribute of the object (e.g. submission type) is in the set."""
    attr: str
    allowed: frozenset
    label: str

    def describe(self) -> str:
        return f"{self.label} is {' | '.join(sorted(s.name for s in self.allowed))}"

    def evaluate(self, snapshot: Snapshot, obj: Any) -> Verdict:
        value = getattr(obj, self.attr)
        if value in self.allowed:
            return HOLDS
        return Verdict(False, (Blocker(f"{self.label} is {getattr(value, 'name', value)}", kind="status"),))


def SubmissionTypeIn(*types: ExtendedEnum) -> AttrIn:
    return AttrIn("submission_type", frozenset(types), "submission type")


@dataclass(frozen=True)
class ChildrenAll(Rule):
    """Every child of the relation is in `ok`. With `nonempty`, there must be at least one child."""
    relation: Relation
    ok: frozenset
    nonempty: bool = False
    ignore_null: bool = True
    """NULL statuses (pooled-submission samples) are not counted, as in legacy SQL comparisons."""

    def describe(self) -> str:
        s = f"all {self.relation.label} are {spec_str(self.ok)}"
        return s + " (at least one)" if self.nonempty else s

    def evaluate(self, snapshot: Snapshot, obj: Any) -> Verdict:
        counts = snapshot.counts(self.relation, obj)
        bad = {s: n for s, n in counts.items() if s not in self.ok and not (s is None and self.ignore_null)}
        if not bad:
            if self.nonempty and not counts:
                return Verdict(False, (Blocker(f"no {self.relation.label}", self.relation),))
            return HOLDS
        total = sum(bad.values())
        ok = spec_str(self.ok)
        expected = f"below {ok[2:]}" if ok.startswith("≥ ") else f"not {ok}"
        counted = sum(n for s, n in counts.items() if not (s is None and self.ignore_null))
        return Verdict(False, (Blocker(
            f"{total} {self.relation.label} {expected} ({_breakdown(bad)})",
            self.relation, frozenset(bad), total, snapshot.sample_ids(self.relation, obj, bad),
            of=counted, breakdown=_short_breakdown(bad),
        ),))


@dataclass(frozen=True)
class ChildrenNone(Rule):
    """No child of the relation is in `bad`."""
    relation: Relation
    bad: frozenset

    def describe(self) -> str:
        return f"no {self.relation.label} is {spec_str(self.bad)}"

    def evaluate(self, snapshot: Snapshot, obj: Any) -> Verdict:
        counts = snapshot.counts(self.relation, obj)
        hit = {s: n for s, n in counts.items() if s in self.bad}
        if not hit:
            return HOLDS
        total = sum(hit.values())
        return Verdict(False, (Blocker(
            f"{_breakdown(hit)} among the {self.relation.label}",
            self.relation, frozenset(hit), total, snapshot.sample_ids(self.relation, obj, hit),
            of=sum(n for s, n in counts.items() if s is not None), breakdown=_short_breakdown(hit),
        ),))


@dataclass(frozen=True)
class ChildrenAny(Rule):
    """At least one child of the relation is in `wanted`."""
    relation: Relation
    wanted: frozenset

    def describe(self) -> str:
        return f"at least one of the {self.relation.label} is {spec_str(self.wanted)}"

    def evaluate(self, snapshot: Snapshot, obj: Any) -> Verdict:
        counts = snapshot.counts(self.relation, obj)
        if any(n for s, n in counts.items() if s in self.wanted):
            return HOLDS
        return Verdict(False, (Blocker(f"none of the {self.relation.label} is {spec_str(self.wanted)}", self.relation),))


@dataclass(frozen=True)
class Predicate(Rule):
    """Escape hatch for conditions that are not about statuses (e.g. 'has a seq run')."""
    text: str
    fn: Callable[[Any, Any], bool] = field(compare=False)
    """fn(session, obj) -> bool"""

    def describe(self) -> str:
        return self.text

    def evaluate(self, snapshot: Snapshot, obj: Any) -> Verdict:
        if self.fn(snapshot.session, obj):
            return HOLDS
        return Verdict(False, (Blocker(f"not: {self.text}"),))


@dataclass(frozen=True, init=False)
class All(Rule):
    rules: tuple[Rule, ...]

    def __init__(self, *rules: Rule) -> None:
        object.__setattr__(self, "rules", tuple(rules))

    def describe(self) -> str:
        return " and ".join(_paren(r) for r in self.rules)

    def evaluate(self, snapshot: Snapshot, obj: Any) -> Verdict:
        blockers: list[Blocker] = []
        for rule in self.rules:
            verdict = rule.evaluate(snapshot, obj)
            blockers.extend(verdict.blockers)
        return Verdict(not blockers, tuple(blockers))


@dataclass(frozen=True, init=False)
class AnyOf(Rule):
    rules: tuple[Rule, ...]

    def __init__(self, *rules: Rule) -> None:
        object.__setattr__(self, "rules", tuple(rules))

    def describe(self) -> str:
        return " or ".join(_paren(r) for r in self.rules)

    def evaluate(self, snapshot: Snapshot, obj: Any) -> Verdict:
        blockers: list[Blocker] = []
        for rule in self.rules:
            verdict = rule.evaluate(snapshot, obj)
            if verdict.holds:
                return HOLDS
            blockers.extend(verdict.blockers)
        return Verdict(False, tuple(blockers))


@dataclass(frozen=True)
class Not(Rule):
    rule: Rule

    def describe(self) -> str:
        return f"not ({self.rule.describe()})"

    def evaluate(self, snapshot: Snapshot, obj: Any) -> Verdict:
        if self.rule.evaluate(snapshot, obj).holds:
            return Verdict(False, (Blocker(f"{self.rule.describe()} holds"),))
        return HOLDS


def _paren(rule: Rule) -> str:
    return f"({rule.describe()})" if isinstance(rule, (All, AnyOf)) else rule.describe()


def _short_breakdown(counts: dict[Any, int]) -> str:
    """Like `_breakdown`, in words for display: '3 accepted, 2 pooled'."""
    return ", ".join(
        f"{n} {'without status' if s is None else s.name.replace('_', ' ').lower()}"
        for s, n in sorted(counts.items(), key=lambda kv: -1 if kv[0] is None else kv[0].id)
    )


def _breakdown(counts: dict[Any, int]) -> str:
    return ", ".join(f"{n} {'no status' if s is None else s.name}" for s, n in sorted(counts.items(), key=lambda kv: -1 if kv[0] is None else kv[0].id))
