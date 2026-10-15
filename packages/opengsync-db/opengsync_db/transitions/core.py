"""Typed building blocks of the status transition registry.

The registry describes *how* statuses change, it does not change them:

- `Entity`     a status-bearing model (one per status column)
- `Effect`     one status change an operation can make on one entity
- `Operation`  something that changes statuses (action, workflow, API call, worker rule, ...)
- `Rule`       a named precondition that can explain why it does not hold (see `rules.py`)
- `Step`/`Route` a named path through operations for one kind of request

The state graph of an entity is the union of the effects of all non-manual operations, so the
graph can never drift from the operations that implement it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Any

from ..categories import ExtendedEnum, OperationKind

if TYPE_CHECKING:
    from .rules import Rule


class _Sentinel:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name


ANY = _Sentinel("ANY")
"""No check on the status (source) or any status the user chooses (destination)."""

NEW = None
"""Source of an effect that creates the entity (no previous status)."""

StatusSpec = frozenset  # frozenset[ExtendedEnum | None] | ANY


def statuses(spec: Any) -> frozenset | _Sentinel:
    """Normalises a status spec: `ANY`, `NEW`, a status, or an iterable of statuses / `NEW`."""
    if spec is ANY:
        return ANY
    if spec is None or isinstance(spec, ExtendedEnum):
        return frozenset([spec])
    return frozenset(spec)


def below(status: ExtendedEnum) -> frozenset:
    """All statuses with a lower id. Legacy code compares by id, so ids >= 10 (failed, rejected, archived) are never below."""
    return frozenset(s for s in type(status) if s.id < status.id)


def at_least(status: ExtendedEnum) -> frozenset:
    """All statuses with an equal or higher id, including the terminal ids >= 10, as legacy `>=` checks do."""
    return frozenset(s for s in type(status) if s.id >= status.id)


def spec_str(spec: frozenset | _Sentinel) -> str:
    if spec is ANY:
        return "any"
    if len(spec) > 1 and None not in spec:  # type: ignore[arg-type]
        enum = type(next(iter(spec)))  # type: ignore[call-overload]
        lowest, highest = min(spec, key=lambda s: s.id), max(spec, key=lambda s: s.id)  # type: ignore[type-var]
        if spec == at_least(lowest):
            return f"≥ {lowest.name}"
        above = [s for s in enum if s.id > highest.id]
        if above and spec == below(min(above, key=lambda s: s.id)):
            return f"< {min(above, key=lambda s: s.id).name}"
    ordered = sorted(spec, key=lambda s: -1 if s is None else s.id)  # type: ignore[arg-type]
    return ", ".join("new" if s is None else s.name for s in ordered)


@dataclass(frozen=True, eq=False)
class Entity:
    """A model with a status column. Identified by its table name."""
    name: str
    """Table name; also stored in `status_change.entity_type`."""
    label: str
    model_name: str
    """Attribute path in `opengsync_db.models`, e.g. `Library` or `links.SeqRequestDeliveryEmailLink`."""
    status_enum: type[ExtendedEnum]
    attr: str = "status"
    nullable: bool = False
    id_attr: str = "id"
    key_attr: str | None = None
    """Second primary key column for composite keys (stored in `status_change.entity_key`)."""
    manual_only: frozenset = frozenset()
    """Statuses only set by hand: in edit forms, or as the chosen status when creating a record."""
    unused: tuple[tuple[ExtendedEnum, str], ...] = ()
    """Statuses that nothing sets, with the reason (documented as gaps)."""
    plural: str = ""

    @property
    def label_plural(self) -> str:
        return self.plural or f"{self.label}s"

    @property
    def model(self) -> type:
        from .. import models
        obj: Any = models
        for part in self.model_name.split("."):
            obj = getattr(obj, part)
        return obj

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Entity) and other.name == self.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return f"Entity[{self.name}]"


@dataclass(frozen=True)
class Effect:
    """One status change an operation can make: `entity: src -> dst`."""
    entity: Entity
    src: frozenset | _Sentinel
    dst: frozenset | _Sentinel
    via: str = "self"
    """Relationship path from the operation's subject, e.g. `libraries` or `seq_request.project` (documentation + validation)."""
    when: str | None = None
    """Condition in plain words, if the change is conditional."""
    gap: str | None = None

    def allows(self, src: ExtendedEnum | None, dst: ExtendedEnum | None) -> bool:
        src_ok = self.src is ANY or src in self.src  # type: ignore[operator]
        dst_ok = self.dst is ANY or dst in self.dst  # type: ignore[operator]
        return src_ok and dst_ok

    @property
    def creates(self) -> bool:
        return self.src is not ANY and NEW in self.src  # type: ignore[operator]

    def __str__(self) -> str:
        s = f"{self.entity.label}: {spec_str(self.src)} → {spec_str(self.dst)}"
        if self.via != "self":
            s += f" (via {self.via})"
        return s


def effect(entity: Entity, src: Any, dst: Any, *, via: str = "self", when: str | None = None, gap: str | None = None) -> Effect:
    return Effect(entity=entity, src=statuses(src), dst=statuses(dst), via=via, when=when, gap=gap)


_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


@dataclass(frozen=True)
class Operation:
    """Something that changes statuses. Code paths run it with `run_operation(session, op, ...)`."""
    id: str
    """Stable slug `area.verb_object`; stored in `operation_run.operation`."""
    label: str
    kind: OperationKind
    subject: Entity | None
    effects: tuple[Effect, ...]
    guard: "Rule | None" = None
    """Precondition for offering the operation in the status tab."""
    reason: str | None = None
    """Reason template (str.format) for implicit kinds, e.g. 'RTAComplete.txt found in {folder}'."""
    where: tuple[str, ...] = ()
    """Code locations, for the docs."""
    doc: str = ""
    gap: str | None = None

    @property
    def area(self) -> str:
        return self.id.split(".")[0]

    @property
    def manual(self) -> bool:
        return self.kind == OperationKind.MANUAL

    def effects_on(self, entity: Entity) -> tuple[Effect, ...]:
        return tuple(e for e in self.effects if e.entity == entity)

    def allows(self, entity: Entity, src: ExtendedEnum | None, dst: ExtendedEnum | None) -> bool:
        return any(e.allows(src, dst) for e in self.effects_on(entity))

    @property
    def reason_hint(self) -> str | None:
        """The reason template for display, its placeholders shown as '…'."""
        return re.sub(r"\{\w+\}", "…", self.reason) if self.reason else None

    def render_reason(self, **ctx: Any) -> str | None:
        if self.reason is None:
            return None
        return self.reason.format(**ctx)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Operation) and other.id == self.id

    def __repr__(self) -> str:
        return f"Operation[{self.id}]"


def operation(
    id: str, label: str, kind: OperationKind, subject: Entity | None, *effects: Effect,
    guard: "Rule | None" = None, reason: str | None = None, where: Iterable[str] = (), doc: str = "", gap: str | None = None,
) -> Operation:
    return Operation(
        id=id, label=label, kind=kind, subject=subject, effects=tuple(effects),
        guard=guard, reason=reason, where=tuple(where), doc=doc, gap=gap,
    )


def valid_operation_id(id: str) -> bool:
    return bool(_ID_RE.match(id)) and len(id) <= 64


@dataclass(frozen=True)
class Step:
    """One step of a route. Any of `alternatives` (operation ids) completes it."""
    id: str
    label: str
    alternatives: tuple[str, ...]
    done_when: "Rule"
    optional: bool = False


@dataclass(frozen=True)
class Route:
    """A named path through operations, e.g. raw samples with in-house library prep."""
    id: str
    label: str
    entity: Entity
    applies: "Rule"
    steps: tuple[Step, ...] = field(default_factory=tuple)
    doc: str = ""
