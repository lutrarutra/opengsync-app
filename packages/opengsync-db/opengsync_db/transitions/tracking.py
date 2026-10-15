"""Records every status change in `operation_run` / `status_change`.

Code that changes statuses runs inside an operation:

    with run_operation(session, ops.lab.POOL_LIBRARIES, subject=lab_prep):
        ...

An `after_flush` hook on `SyncSession` reads the status attributes of new and changed objects,
writes one `operation_run` per operation (lazily, on its first change) and one `status_change`
per changed record, with Core inserts on the session's connection: same transaction, never seen
by the unit of work or the HTTP audit log. Changes outside any operation are recorded under
`system.unattributed`, with the code location as the reason.

The mode in `session.info["transitions.mode"]` (default: `OPENGSYNC_TRANSITIONS_MODE`, else
`warn`) decides what happens with a change the operation does not declare, or no operation at all:
`record` writes it silently, `warn` also logs it (once per location), `strict` raises.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

import sqlalchemy as sa
from loguru import logger
from sqlalchemy import event, inspect, orm

from ..categories import ExtendedEnum, OperationKind
from .core import Entity, Operation
from . import entities as E

STACK_KEY = "transitions.op_stack"
ACTOR_KEY = "transitions.actor_id"
MODE_KEY = "transitions.mode"
MODE_ENV = "OPENGSYNC_TRANSITIONS_MODE"
MODES = ("record", "warn", "strict")

UNATTRIBUTED = "system.unattributed"
MAX_TEXT = 512


class UndeclaredTransition(Exception):
    """Strict mode: a status changed outside an operation, or in a way the operation does not declare."""


@dataclass(eq=False)
class OperationContext:
    """The running operation. `detail(obj, text)` attaches a note to the change of one record."""
    operation: Operation
    subject_type: str | None
    subject_id: int | None
    actor_id: int | None
    comment: str | None
    reason: str | None
    parent: "OperationContext | None"
    details: dict[tuple[str, Any, Any], str] = field(default_factory=dict)
    run_id: int | None = None

    def detail(self, obj: Any, text: str) -> None:
        entity = entity_of(obj)
        if entity is None:
            raise ValueError(f"{type(obj).__name__} has no tracked status")
        self.details[_identity(entity, obj)] = text[:MAX_TEXT]


def _models_by_class() -> dict[type, Entity]:
    global _BY_CLASS
    if _BY_CLASS is None:
        _BY_CLASS = {entity.model: entity for entity in E.ENTITIES}
    return _BY_CLASS


_BY_CLASS: dict[type, Entity] | None = None


def entity_of(obj: Any) -> Entity | None:
    return _models_by_class().get(type(obj))


def _identity(entity: Entity, obj: Any) -> tuple[str, Any, Any]:
    key = getattr(obj, entity.key_attr) if entity.key_attr else None
    return (entity.name, getattr(obj, entity.id_attr), key)


def _stack(session: orm.Session) -> list[OperationContext]:
    return session.info.setdefault(STACK_KEY, [])


def current(session: orm.Session) -> OperationContext | None:
    stack = session.info.get(STACK_KEY)
    return stack[-1] if stack else None


def mode(session: orm.Session) -> str:
    value = session.info.get(MODE_KEY) or os.environ.get(MODE_ENV) or "warn"
    if value not in MODES:
        raise ValueError(f"unknown transitions mode '{value}', expected one of {MODES}")
    return value


def set_actor(session: orm.Session, actor_id: int | None) -> None:
    """Default actor for everything this session does (the logged-in user of a request)."""
    session.info[ACTOR_KEY] = actor_id


def _resolve(op: Operation | str) -> Operation:
    if isinstance(op, Operation):
        return op
    from .registry import registry
    return registry()[op]


def _reason(op: Operation, reason: str | None, ctx: dict[str, Any]) -> str | None:
    if reason is None and op.reason is not None:
        try:
            reason = op.reason.format(**ctx)
        except KeyError as e:
            if op.kind.implicit:
                raise ValueError(f"{op.id}: reason template '{op.reason}' needs {e}") from None
            reason = None
    if op.kind.implicit and not (reason and reason.strip()):
        raise ValueError(f"{op.id}: {op.kind.name} operations need a reason")
    return reason[:MAX_TEXT] if reason else None


@contextmanager
def run_operation(
    session: orm.Session,
    op: Operation | str,
    subject: Any = None,
    actor_id: int | None = None,
    comment: str | None = None,
    reason: str | None = None,
    **reason_ctx: Any,
) -> Iterator[OperationContext]:
    """Runs `op`: status changes made inside are recorded under one `operation_run`.

    Flushes on enter (pending changes belong to the outer context) and on successful exit
    (changes are attributed before the caller commits). Worker, migration and system operations
    need a reason: pass `reason=` or the keys of the operation's reason template.
    """
    op = _resolve(op)
    reason = _reason(op, reason, reason_ctx)
    parent = current(session)
    subject_type = subject_id = None
    if subject is not None:
        entity = entity_of(subject)
        subject_type = entity.name if entity else inspect(subject).mapper.local_table.name
        subject_id = getattr(subject, entity.id_attr if entity else "id", None)
    if actor_id is None:
        actor_id = parent.actor_id if parent is not None else session.info.get(ACTOR_KEY)

    session.flush()
    context = OperationContext(
        operation=op, subject_type=subject_type, subject_id=subject_id, actor_id=actor_id,
        comment=comment.strip()[:MAX_TEXT] if comment and comment.strip() else None,
        reason=reason, parent=parent,
    )
    stack = _stack(session)
    stack.append(context)
    try:
        yield context
        session.flush()
    finally:
        if stack and stack[-1] is context:
            stack.pop()
        elif context in stack:
            stack.remove(context)


# -- flush hook -----------------------------------------------------------------------------------

def _tables():
    from ..models import OperationRun, StatusChange
    return OperationRun.__table__, StatusChange.__table__


def _normalise(entity: Entity, value: Any) -> ExtendedEnum | None:
    if value is None:
        return None
    if isinstance(value, entity.status_enum):
        return value
    return entity.status_enum.get(int(value))


def _collect(session: orm.Session) -> list[tuple[Entity, Any, ExtendedEnum | None, ExtendedEnum | None]]:
    by_class = _models_by_class()
    changes = []
    for obj in session.new:
        if (entity := by_class.get(type(obj))) is None:
            continue
        dst = _normalise(entity, getattr(obj, entity.attr))
        if dst is not None:
            changes.append((entity, obj, None, dst))
    for obj in session.dirty:
        if (entity := by_class.get(type(obj))) is None or obj in session.deleted:
            continue
        history = inspect(obj).attrs[entity.attr].history
        if not history.added and not history.deleted:
            continue
        src = _normalise(entity, history.deleted[0]) if history.deleted else None
        dst = _normalise(entity, history.added[0]) if history.added else None
        if src != dst:
            changes.append((entity, obj, src, dst))
    return changes


def _caller_location() -> str:
    """First stack frame outside SQLAlchemy and this package's session/tracking code."""
    skip = ("sqlalchemy", "opengsync_db.transitions", "opengsync_db.core.SyncSession", "contextlib")
    frame = sys._getframe(1)
    while frame is not None:
        module = frame.f_globals.get("__name__", "")
        if not module.startswith(skip):
            return f"{module}:{frame.f_code.co_name}:{frame.f_lineno}"
        frame = frame.f_back  # type: ignore[assignment]
    return "unknown"


def _insert_run(connection: sa.Connection, **values: Any) -> int:
    run_table, _ = _tables()
    stmt = sa.insert(run_table).values(inferred=False, **values).returning(run_table.c.id)
    return connection.execute(stmt).scalar_one()


def _ensure_run(connection: sa.Connection, context: OperationContext) -> int:
    if context.run_id is None:
        parent_id = _ensure_run(connection, context.parent) if context.parent is not None else None
        context.run_id = _insert_run(
            connection,
            operation=context.operation.id, kind=context.operation.kind, actor_id=context.actor_id,
            subject_type=context.subject_type, subject_id=context.subject_id, parent_run_id=parent_id,
            comment=context.comment, reason=context.reason,
        )
    return context.run_id


_warned: set[str] = set()


def _report(session: orm.Session, message: str, key: str) -> None:
    current_mode = mode(session)
    if current_mode == "strict":
        raise UndeclaredTransition(message)
    if current_mode == "warn" and key not in _warned:
        _warned.add(key)
        logger.warning(f"[transitions] {message}")


@event.listens_for(orm.Session, "after_flush")
def _record_status_changes(session: orm.Session, flush_context: Any) -> None:
    changes = _collect(session)
    if not changes:
        return

    connection = session.connection()
    context = current(session)
    if context is None:
        location = _caller_location()
        _report(session, f"status changed outside an operation at {location}: " + ", ".join(
            f"{entity.name} {getattr(obj, entity.id_attr)} {_name(src)} → {_name(dst)}" for entity, obj, src, dst in changes
        ), key=f"unattributed:{location}")
        run_id = _insert_run(
            connection, operation=UNATTRIBUTED, kind=OperationKind.SYSTEM, actor_id=session.info.get(ACTOR_KEY),
            reason=f"no operation context at {location}"[:MAX_TEXT],
        )
        details: dict = {}
    else:
        run_id = _ensure_run(connection, context)
        details = context.details

    _, change_table = _tables()
    rows = []
    for entity, obj, src, dst in changes:
        declared = context is not None and context.operation.allows(entity, src, dst)
        if context is not None and not declared:
            _report(
                session,
                f"{context.operation.id} does not declare {entity.label}: {_name(src)} → {_name(dst)} ({entity.name} {getattr(obj, entity.id_attr)})",
                key=f"undeclared:{context.operation.id}:{entity.name}:{_name(src)}:{_name(dst)}",
            )
        identity = _identity(entity, obj)
        rows.append(dict(
            run_id=run_id, entity_type=entity.name, entity_id=identity[1], entity_key=identity[2],
            from_status=None if src is None else src.id, to_status=None if dst is None else dst.id,
            declared=declared, inferred=False, detail=details.get(identity),
        ))
    connection.execute(sa.insert(change_table), rows)


def _name(status: ExtendedEnum | None) -> str:
    return "new" if status is None else status.name


@event.listens_for(orm.Session, "after_rollback")
@event.listens_for(orm.Session, "after_soft_rollback")
def _forget_runs(session: orm.Session, *args: Any) -> None:
    """Runs written in a rolled-back transaction are gone; recreate them on the next change."""
    for context in session.info.get(STACK_KEY) or ():
        context.run_id = None
