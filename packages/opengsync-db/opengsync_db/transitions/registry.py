"""The registry: all operations and routes, with validation and lookups.

`validate()` is run by tests and the docs CLI, never at import, so a registry mistake can't stop
the app or the worker from starting.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import sqlalchemy as sa

from ..categories import ExtendedEnum, OperationKind
from .core import ANY, Effect, Entity, Operation, Route, valid_operation_id
from . import entities as E


class RegistryError(Exception):
    pass


GRAPH_KINDS = frozenset([OperationKind.ACTION, OperationKind.WORKFLOW, OperationKind.API, OperationKind.WORKER])
"""Kinds whose effects form the state graph (manual edits, migrations and system changes are not process steps)."""


@dataclass(frozen=True)
class Edge:
    entity: Entity
    src: ExtendedEnum | None
    dst: ExtendedEnum
    operation: Operation
    effect: Effect


class Registry:
    def __init__(self, operations: Iterable[Operation], routes: Iterable[Route], entities: Iterable[Entity] = E.ENTITIES) -> None:
        self.entities = tuple(entities)
        self.operations: dict[str, Operation] = {}
        self._duplicates: list[str] = []
        for op in operations:
            if op.id in self.operations:
                self._duplicates.append(op.id)
            self.operations[op.id] = op
        self.routes: dict[str, Route] = {r.id: r for r in routes}

    @classmethod
    def default(cls) -> "Registry":
        from .operations import MODULES
        from .routes import ROUTES
        return cls([op for module in MODULES for op in module.ALL], ROUTES)

    def __getitem__(self, id: str) -> Operation:
        return self.operations[id]

    # -- lookups ----------------------------------------------------------------------------------

    def edges(self, entity: Entity) -> list[Edge]:
        """Explicit process edges of an entity: effects of non-manual operations with a concrete destination.
        `ANY` sources are expanded; `ANY` destinations ('chosen status') are not edges."""
        edges = []
        for op in self.operations.values():
            if op.kind not in GRAPH_KINDS:
                continue
            for eff in op.effects_on(entity):
                if eff.dst is ANY:
                    continue
                srcs = list(entity.status_enum) if eff.src is ANY else list(eff.src)  # type: ignore[arg-type]
                for src in srcs:
                    for dst in eff.dst:  # type: ignore[union-attr]
                        if src != dst:
                            edges.append(Edge(entity, src, dst, op, eff))
        return edges

    def operations_reaching(self, entity: Entity, dst: ExtendedEnum, src: ExtendedEnum | None = ...) -> list[Operation]:  # type: ignore[assignment]
        """All operations that can set `entity` to `dst` (from `src`, if given)."""
        out = []
        for op in self.operations.values():
            for eff in op.effects_on(entity):
                dst_ok = eff.dst is ANY or dst in eff.dst  # type: ignore[operator]
                src_ok = src is ... or eff.src is ANY or src in eff.src  # type: ignore[operator]
                if dst_ok and src_ok and op.kind not in (OperationKind.MIGRATION, OperationKind.SYSTEM):
                    out.append(op)
                    break
        return out

    def outgoing(self, entity: Entity, status: ExtendedEnum | None) -> dict[ExtendedEnum, list[Operation]]:
        """Process edges leaving `status`, grouped by destination."""
        out: dict[ExtendedEnum, list[Operation]] = defaultdict(list)
        for edge in self.edges(entity):
            if edge.src == status and edge.operation not in out[edge.dst]:
                out[edge.dst].append(edge.operation)
        return dict(out)

    def allows(self, op: Operation, entity: Entity, src: ExtendedEnum | None, dst: ExtendedEnum | None) -> bool:
        return op.allows(entity, src, dst)

    def gaps(self) -> list[tuple[str, str]]:
        """(where, text) for every documented gap."""
        out = []
        for entity in self.entities:
            for status, text in entity.unused:
                out.append((f"{entity.label} {status.name}", text))
        for op in self.operations.values():
            if op.gap:
                out.append((op.id, op.gap))
            for eff in op.effects:
                if eff.gap:
                    out.append((f"{op.id} ({eff})", eff.gap))
        return out

    # -- validation -------------------------------------------------------------------------------

    def validate(self, resolve_relations: bool = True) -> None:
        errors = self.problems(resolve_relations)
        if errors:
            raise RegistryError("Invalid transition registry:\n- " + "\n- ".join(errors))

    def problems(self, resolve_relations: bool = True) -> list[str]:
        errors = [f"duplicate operation id '{id}'" for id in self._duplicates]

        for op in self.operations.values():
            if not valid_operation_id(op.id):
                errors.append(f"operation id '{op.id}' is not a slug like 'area.verb_object'")
            if op.kind.implicit and not op.reason:
                errors.append(f"{op.id}: {op.kind.name} operations need a reason template")
            for eff in op.effects:
                if eff.entity not in self.entities:
                    errors.append(f"{op.id}: unknown entity {eff.entity}")
                for spec in (eff.src, eff.dst):
                    if spec is ANY:
                        continue
                    for s in spec:  # type: ignore[union-attr]
                        if s is not None and not isinstance(s, eff.entity.status_enum):
                            errors.append(f"{op.id}: {s!r} is not a {eff.entity.status_enum.__name__}")
                if eff.dst is not ANY and None in eff.dst:  # type: ignore[operator]
                    errors.append(f"{op.id}: an effect cannot set the status to NULL")
                if resolve_relations and op.subject is not None and eff.via != "self":
                    if (err := _check_path(op.subject, eff.via)) is not None:
                        errors.append(f"{op.id}: {err}")

        for entity in self.entities:
            reached: set = set()
            for op in self.operations.values():
                if op.kind not in GRAPH_KINDS:
                    continue
                for eff in op.effects_on(entity):
                    if eff.dst is not ANY:
                        reached.update(eff.dst)  # type: ignore[arg-type]
            documented = set(entity.manual_only) | {s for s, _ in entity.unused}
            for status in entity.status_enum:
                if status not in reached and status not in documented:
                    errors.append(f"{entity.label} {status.name} is set by no operation; declare it or list it in manual_only/unused")
                if status in reached and status in documented:
                    errors.append(f"{entity.label} {status.name} is listed as manual_only/unused but set by an operation")

        for route in self.routes.values():
            for step in route.steps:
                for op_id in step.alternatives:
                    if op_id not in self.operations:
                        errors.append(f"route {route.id}, step {step.id}: unknown operation '{op_id}'")
        return errors


def _check_path(subject: Entity, path: str) -> str | None:
    """Every segment of `path` must be a relationship, starting from the subject's model."""
    model = subject.model
    for part in path.split("."):
        mapper = sa.inspect(model)
        if part not in mapper.relationships:
            return f"'{part}' in '{path}' is not a relationship of {model.__name__}"
        model = mapper.relationships[part].mapper.class_
    return None


_default: Registry | None = None


def registry() -> Registry:
    """The registry of all declared operations and routes (built on first use)."""
    global _default
    if _default is None:
        _default = Registry.default()
    return _default
