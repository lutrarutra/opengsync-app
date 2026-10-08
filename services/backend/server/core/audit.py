from fastapi import Request
from fastapi.routing import APIRoute
from sqlalchemy import event, inspect, orm

from opengsync_db import SyncSession

class AuditLogger:
    def __init__(self, request: Request):
        route: APIRoute | None = request.scope.get("route")
        self.route = route.path if route else request.url.path
        self.method = request.method.upper()

        self.resource_id: str | None = None
        self.metadata: dict = {}

        request.state.audit = self


# ── DB change tracking ────────────────────────────────────────────────
# Every flush records what it wrote into ``session.info`` as pending; a commit
# moves pending changes to committed, a rollback discards only the pending
# ones. DBSessionCleanupMiddleware pops the committed changes after it commits
# and writes them to the audit log, so only committed writes are audited.

_PENDING_KEY = "audit_pending"
_COMMITTED_KEY = "audit_committed"
_MAX_IDS = 100  # per (table, op); ``count`` stays exact

# Tables whose writes are not worth an audit line on their own.
IGNORED_TABLES: frozenset[str] = frozenset()


def _new_entry(table: str, op: str) -> dict:
    return {"table": table, "op": op, "count": 0, "ids": [], "fields": set(), "bulk": False}


def _record(session: orm.Session, table: str, op: str, pk=None, fields=(), bulk: bool = False) -> None:
    if table in IGNORED_TABLES:
        return
    pending: dict = session.info.setdefault(_PENDING_KEY, {})
    entry = pending.setdefault((table, op), _new_entry(table, op))
    entry["count"] += 1
    entry["bulk"] |= bulk
    if pk is not None and len(entry["ids"]) < _MAX_IDS:
        entry["ids"].append(pk)
    entry["fields"].update(fields)


def _primary_key(obj):
    pk = inspect(obj).mapper.primary_key_from_instance(obj)
    return pk[0] if len(pk) == 1 else pk


@event.listens_for(SyncSession, "after_flush")
def _collect_flush(session: orm.Session, flush_context) -> None:
    # new/dirty/deleted and attribute history still show the pre-flush state here
    for obj in session.new:
        _record(session, inspect(obj).mapper.local_table.name, "insert", _primary_key(obj))
    for obj in session.dirty:
        fields = [attr.key for attr in inspect(obj).attrs if attr.history.has_changes()]
        if fields:
            _record(session, inspect(obj).mapper.local_table.name, "update", _primary_key(obj), fields)
    for obj in session.deleted:
        _record(session, inspect(obj).mapper.local_table.name, "delete", _primary_key(obj))


@event.listens_for(SyncSession, "do_orm_execute")
def _collect_bulk(state: orm.ORMExecuteState) -> None:
    # bulk insert/update/delete statements bypass the unit of work (and after_flush)
    if not (state.is_insert or state.is_update or state.is_delete):
        return
    table = getattr(state.statement, "table", None)
    if table is None:
        return
    op = "insert" if state.is_insert else "update" if state.is_update else "delete"
    _record(state.session, table.name, op, bulk=True)


@event.listens_for(SyncSession, "after_commit")
def _commit_changes(session: orm.Session) -> None:
    committed: dict = session.info.setdefault(_COMMITTED_KEY, {})
    for key, entry in (session.info.pop(_PENDING_KEY, None) or {}).items():
        if (target := committed.get(key)) is None:
            committed[key] = entry
            continue
        target["count"] += entry["count"]
        target["bulk"] |= entry["bulk"]
        target["fields"] |= entry["fields"]
        target["ids"].extend(entry["ids"][:_MAX_IDS - len(target["ids"])])


@event.listens_for(SyncSession, "after_rollback")
def _discard_changes(session: orm.Session) -> None:
    session.info.pop(_PENDING_KEY, None)


def pop_changes(session: orm.Session) -> list[dict]:
    """Return and clear the changes committed since the last pop."""
    changes: dict = session.info.pop(_COMMITTED_KEY, None) or {}
    result = []
    for entry in sorted(changes.values(), key=lambda e: (e["table"], e["op"])):
        entry = dict(entry)
        entry["fields"] = sorted(entry["fields"])
        if not entry["fields"]:
            del entry["fields"]
        if not entry["bulk"]:
            del entry["bulk"]
        result.append(entry)
    return result
