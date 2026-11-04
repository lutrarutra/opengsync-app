"""Invalidation of the cached access levels (``access:<model>:<id>:user:<viewer>``, see dependencies.py).

Access levels depend on object status (e.g. WRITE only while a request is a draft), ownership, group
membership and the viewer's role. Every flush records the Redis key patterns that such a change makes
stale; a commit moves them to committed, a rollback discards them. DBSessionCleanupMiddleware deletes
the committed patterns right after it commits, so a concurrent request cannot re-cache the old level
from the not yet committed state, and a rolled back change does not drop the cache.
"""
from typing import Callable, Iterable

from loguru import logger
from redis import ConnectionPool, Redis
from sqlalchemy import event, inspect, orm

from opengsync_db import SyncSession

_PENDING_KEY = "access_cache_pending"
_COMMITTED_KEY = "access_cache_committed"

# Child namespaces are cleared as a whole on a parent change: it is a cache, and finding the children
# would need queries inside the flush.
_SEQ_REQUEST_CHILDREN = ("access:library:*", "access:pool:*", "access:media_file:*")

# table -> (attributes whose change affects access, patterns to delete for the changed object)
WATCHED: dict[str, tuple[frozenset[str], Callable[[object], Iterable[str]]]] = {
    "seq_request": (
        frozenset({"status", "group_id", "requestor_id"}),
        lambda o: (f"access:seq_request:{o.id}:*", *_SEQ_REQUEST_CHILDREN),
    ),
    "project": (
        frozenset({"status", "owner_id", "group_id"}),
        lambda o: (f"access:project:{o.id}:*", "access:sample:*"),
    ),
    "sample": (frozenset({"status", "project_id"}), lambda o: (f"access:sample:{o.id}:*",)),
    "library": (frozenset({"seq_request_id"}), lambda o: (f"access:library:{o.id}:*",)),
    "pool": (frozenset({"seq_request_id"}), lambda o: (f"access:pool:{o.id}:*",)),
    "media_file": (frozenset({"seq_request_id", "uploader_id"}), lambda o: (f"access:media_file:{o.id}:*",)),
    "user_affiliation": (
        frozenset({"affiliation_type", "user_id", "group_id"}),
        lambda o: (f"access:*:user:{o.user_id}", f"access:group:{o.group_id}:*"),
    ),
    "lims_user": (frozenset({"role"}), lambda o: (f"access:*:user:{o.id}", f"user:{o.id}")),
}

# Tables whose inserts change access (a new member gains access to the group's objects).
_INSERT_TABLES = frozenset({"user_affiliation"})

# Namespaces of dependencies.py whose entries the patterns above keep fresh. ``user`` and ``group``
# levels only depend on the viewer's role and affiliations, which are covered by the viewer patterns.
INVALIDATED_NAMESPACES = frozenset({
    "seq_request", "project", "sample", "library", "pool", "media_file", "group", "user",
})


def add(session: orm.Session, *patterns: str) -> None:
    """Delete these key patterns once the session commits (for changes the flush listener can't see)."""
    session.info.setdefault(_PENDING_KEY, set()).update(patterns)


def _table(obj) -> str:
    return inspect(obj).mapper.local_table.name


@event.listens_for(SyncSession, "after_flush")
def _collect_flush(session: orm.Session, flush_context) -> None:
    # new/dirty/deleted and attribute history still show the pre-flush state here
    for obj in session.new:
        if (table := _table(obj)) in _INSERT_TABLES:
            add(session, *WATCHED[table][1](obj))
    for obj in session.dirty:
        if (watched := WATCHED.get(_table(obj))) is None:
            continue
        attrs, patterns = watched
        state = inspect(obj)
        if any(state.attrs[key].history.has_changes() for key in attrs if key in state.attrs):
            add(session, *patterns(obj))
            if _table(obj) == "user_affiliation":  # a moved affiliation also changes the old user/group
                for key, prefix in (("user_id", "access:*:user:{}"), ("group_id", "access:group:{}:*")):
                    for old in state.attrs[key].history.deleted or ():
                        add(session, prefix.format(old))
    for obj in session.deleted:
        if (watched := WATCHED.get(_table(obj))) is not None:
            add(session, *watched[1](obj))


@event.listens_for(SyncSession, "do_orm_execute")
def _collect_bulk(state: orm.ORMExecuteState) -> None:
    # bulk update/delete statements bypass the unit of work: drop every access level
    if not (state.is_update or state.is_delete or state.is_insert):
        return
    table = getattr(state.statement, "table", None)
    if table is not None and table.name in WATCHED:
        add(state.session, "access:*", *(("user:*",) if table.name == "lims_user" else ()))


@event.listens_for(SyncSession, "after_commit")
def _commit_patterns(session: orm.Session) -> None:
    if pending := session.info.pop(_PENDING_KEY, None):
        session.info.setdefault(_COMMITTED_KEY, set()).update(pending)


@event.listens_for(SyncSession, "after_rollback")
def _discard_patterns(session: orm.Session) -> None:
    session.info.pop(_PENDING_KEY, None)


def pop_patterns(session: orm.Session) -> set[str]:
    """Return and clear the patterns committed since the last pop."""
    return session.info.pop(_COMMITTED_KEY, None) or set()


def invalidate_committed(session: orm.Session, redis_pool: ConnectionPool | None) -> None:
    """Delete the cache keys made stale by the committed changes of this session."""
    patterns = pop_patterns(session)
    if not patterns or redis_pool is None:
        return
    if "access:*" in patterns:  # covers every other access pattern
        patterns = {p for p in patterns if not p.startswith("access:")} | {"access:*"}
    try:
        with Redis(connection_pool=redis_pool) as redis:
            if keys := [p for p in patterns if "*" not in p]:
                redis.delete(*keys)
            for pattern in sorted(p for p in patterns if "*" in p):
                for batch in _batched(redis.scan_iter(match=pattern, count=500), 500):
                    redis.delete(*batch)
    except Exception:
        # a failed invalidation must not fail the committed request; the TTL bounds the staleness
        logger.exception(f"Failed to invalidate access cache: {sorted(patterns)}")


def _batched(iterable, size: int):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
