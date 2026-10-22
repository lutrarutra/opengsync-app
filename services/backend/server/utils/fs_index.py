"""Search over the fs-index (opengsync_db.fs_index), the worker-maintained SQLite index of share_root.

The index can be minutes (new data) to a day (deep, unchanged data) behind the mount; browsing stays live
and anything shared is validated live, so search results are only a way to find paths.
"""
import json
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import sqlalchemy as sa
from loguru import logger
from redis.exceptions import RedisError
from sqlalchemy import orm

from opengsync_db import SyncSession, models
from opengsync_db.fs_index import Entry, Meta, subtree_bounds

from ..core import config
from ..core.redis import RedisClient
from .file_browser import file_icon

# Read by the crawler (opengsync_worker.tasks.fs_index_crawl_wrapper), which checks these directories first.
TOUCH_KEY = "fs-index:touch"
# Held by the worker while it imports or crawls (opengsync_worker.tasks._with_fs_index_lock).
LOCK_KEY = "fs-index:writer-lock"
DUMP_SUFFIX = ".jsonl.gz"
MIN_TERM_LENGTH = 3
PAGE_SIZE = 50
Kind = Literal["all", "dirs", "files"]

class QueryTooShort(ValueError):
    pass


@dataclass
class SearchResult:
    """One row of the search results (templates/components/file-browser/search-results.html)."""
    path: str
    name: str
    # (label, share-root relative path) of each parent folder, root first
    parents: list[tuple[str, str]]
    is_dir: bool
    is_link: bool
    size: int
    mtime: int
    hidden: bool
    unsafe: bool
    icon: str
    # the name split into (text, matches the query)
    name_parts: list[tuple[str, bool]]
    data_paths: list[models.DataPath] = field(default_factory=list)

    @property
    def parent(self) -> str:
        return self.parents[-1][1] if self.parents else ""

    @property
    def suffix(self) -> str:
        return Path(self.name).suffix.lower()


@dataclass
class SearchPage:
    results: list[SearchResult]
    has_more: bool


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _prefix_clause(prefixes: Sequence[str], params: dict, name: str = "p") -> str:
    clauses = []
    for i, prefix in enumerate(prefixes):
        prefix = prefix.strip("/")
        params[f"{name}{i}"] = prefix
        params[f"{name}lo{i}"], params[f"{name}hi{i}"] = subtree_bounds(prefix)
        clauses.append(f"(e.path = :{name}{i} OR (e.path >= :{name}lo{i} AND e.path < :{name}hi{i}))")
    return "(" + " OR ".join(clauses) + ")"


def _path_query(query: str) -> str | None:
    """A query with a slash is a path (prefix): absolute under share_root, or share-root relative."""
    if "/" not in query:
        return None
    share_root = config.settings.app_config.share_root.rstrip("/")
    if query == share_root or query.startswith(share_root + "/"):
        query = query[len(share_root):]
    return query.strip("/") or None


def search(
    session: SyncSession,
    query: str,
    prefixes: Sequence[str] | None = None,
    visible_only: bool = False,
    kind: Kind = "all",
    root: str | None = None,
    limit: int = PAGE_SIZE,
    offset: int = 0,
) -> list[Entry]:
    """Entries whose name contains every word of `query` (case-insensitive); with a slash, entries under
    that path. Exact name matches first, then directories, then most recently changed.

    `prefixes` limits results to those paths and their descendants (an empty list matches nothing);
    `visible_only` drops what share links hide (.ngsignore, symlinks leaving the share);
    `root` limits results to one top-level folder of the share.
    """
    if prefixes is not None and not prefixes:
        return []
    query = query.strip()
    params: dict = {"limit": limit, "offset": offset}
    where = ["e.searchable"]
    if visible_only:
        where.append("NOT e.hidden AND NOT e.unsafe")
    if prefixes is not None:
        where.append(_prefix_clause(prefixes, params))
    if root:
        where.append(_prefix_clause([root], params, name="r"))
    if kind == "dirs":
        where.append("(e.kind = 'd' OR (e.kind = 'l' AND e.target_kind = 'd'))")
    elif kind == "files":
        where.append("NOT (e.kind = 'd' OR (e.kind = 'l' AND e.target_kind = 'd'))")

    if (path := _path_query(query)) is not None:
        params["path"] = path
        params["path_end"] = path + "\U0010ffff"
        statement = (
            "SELECT e.* FROM entry e WHERE e.path >= :path AND e.path < :path_end AND "
            + " AND ".join(where) + " ORDER BY e.path LIMIT :limit OFFSET :offset"
        )
    else:
        words = query.split()
        long_words = [word for word in words if len(word) >= MIN_TERM_LENGTH]
        if not long_words:
            raise QueryTooShort(f"Type at least {MIN_TERM_LENGTH} characters.")
        params["match"] = " ".join('"' + word.replace('"', '""') + '"' for word in long_words)
        for i, word in enumerate(word for word in words if len(word) < MIN_TERM_LENGTH):
            params[f"w{i}"] = f"%{_like_escape(word)}%"
            where.append(f"e.name LIKE :w{i} ESCAPE '\\'")
        params["exact"] = query.lower()
        statement = (
            "SELECT e.* FROM entry_fts JOIN entry e ON e.id = entry_fts.rowid "
            "WHERE entry_fts MATCH :match AND " + " AND ".join(where) + " "
            "ORDER BY lower(e.name) = :exact DESC, e.kind = 'd' DESC, COALESCE(e.max_mtime, e.mtime) DESC "
            "LIMIT :limit OFFSET :offset"
        )
    return list(session.execute(sa.select(Entry).from_statement(sa.text(statement).bindparams(**params))).scalars())


def search_page(session: SyncSession, query: str, page: int = 0, **kwargs) -> tuple[list[Entry], bool]:
    """One page of `search` and whether there are more."""
    entries = search(session, query, limit=PAGE_SIZE + 1, offset=page * PAGE_SIZE, **kwargs)
    return entries[:PAGE_SIZE], len(entries) > PAGE_SIZE


def roots(session: SyncSession) -> list[str]:
    """Top-level folders of the share that are in the index."""
    return list(session.execute(sa.select(Entry.path).where(Entry.parent_id.is_(None)).order_by(Entry.path)).scalars())


def indexed_at(session: SyncSession | None) -> int | None:
    """Unix time of the last import or crawl."""
    if session is None:
        return None
    values = session.execute(
        sa.select(Meta.value).where(sa.or_(Meta.key == "crawled_at", Meta.key.like("imported_at:%")))
    ).scalars()
    timestamps = [int(value) for value in values if value and value.isdigit()]
    return max(timestamps) if timestamps else None


def highlight(name: str, query: str) -> list[tuple[str, bool]]:
    """`name` split into (text, matches a word of `query`) parts, matches compared case-insensitively."""
    words = sorted({word.lower() for word in query.split() if "/" not in word}, key=len, reverse=True)
    lower = name.lower()
    marked = [False] * len(name)
    for word in words:
        start = lower.find(word)
        while start != -1:
            for i in range(start, start + len(word)):
                marked[i] = True
            start = lower.find(word, start + len(word))
    parts: list[tuple[str, bool]] = []
    for char, is_match in zip(name, marked):
        if parts and parts[-1][1] == is_match:
            parts[-1] = (parts[-1][0] + char, is_match)
        else:
            parts.append((char, is_match))
    return parts


def entry_size(entry: Entry) -> int | None:
    """A folder's total, a symlink's target's size, or a file's size."""
    if entry.kind == "d":
        return entry.total_size
    if entry.kind == "l":
        return entry.target_size
    return entry.size


def path_sizes(session: SyncSession, paths: Sequence[str]) -> dict[str, int]:
    """Sizes of share-root relative paths (as in SharePath.path); paths not in the index are left out."""
    if not paths:
        return {}
    entries = session.execute(sa.select(Entry).where(Entry.path.in_(set(paths)))).scalars()
    return {entry.path: size for entry in entries if (size := entry_size(entry)) is not None}


def to_results(entries: Sequence[Entry], query: str, session: SyncSession | None = None) -> list[SearchResult]:
    """Result rows from index entries. With a session, each row also carries the data paths registered on
    it (insider browser badges)."""
    by_path: dict[str, list[models.DataPath]] = {}
    if session is not None and entries:
        data_paths = session.execute(
            sa.select(models.DataPath)
            .where(models.DataPath.path.in_([entry.path for entry in entries]))
            .options(
                orm.joinedload(models.DataPath.project),
                orm.joinedload(models.DataPath.seq_request),
                orm.joinedload(models.DataPath.library),
                orm.joinedload(models.DataPath.experiment),
            )
        ).unique().scalars()
        for data_path in data_paths:
            by_path.setdefault(data_path.path, []).append(data_path)

    results = []
    for entry in entries:
        is_dir = entry.kind == "d" or (entry.kind == "l" and entry.target_kind == "d")
        components = entry.path.split("/")
        results.append(SearchResult(
            path=entry.path,
            name=entry.name,
            parents=[(label, "/".join(components[: i + 1])) for i, label in enumerate(components[:-1])],
            is_dir=is_dir,
            is_link=entry.kind == "l",
            size=entry_size(entry) or 0,
            mtime=entry.mtime or entry.max_mtime or 0,
            hidden=entry.hidden,
            unsafe=entry.unsafe,
            icon=file_icon(entry.name, is_dir),
            name_parts=highlight(entry.name, query),
            data_paths=by_path.get(entry.path, []),
        ))
    return results


def touch(redis: RedisClient | None, path: str | Path) -> None:
    """Ask the crawler to re-check a directory the app just listed live."""
    if redis is None or not config.settings.app_config.fs_index.enabled:
        return
    path = Path(path).as_posix().strip("/")
    if not path or path == ".":
        return
    try:
        redis.sadd(TOUCH_KEY, path)
    except RedisError:
        logger.exception(f"Failed to queue {path} for the fs-index crawler")


@dataclass
class RootStatus:
    name: str
    total_size: int
    n_files: int
    # unix time of the last dump import, None when the crawler built it alone
    imported_at: int | None = None
    dump_started_at: str | None = None
    import_seconds: float | None = None


@dataclass
class IndexStatus:
    """What the insider dashboard shows about the fs-index and its worker tasks."""
    db_file: str
    available: bool = False
    db_size: int | None = None
    # None when Redis could not be asked
    running: bool | None = None
    queued: int | None = None
    last_crawl: dict | None = None
    last_change_at: int | None = None
    # directories whose check is due, and due for over an hour (the crawler is falling behind)
    due: int = 0
    overdue: int = 0
    roots: list[RootStatus] = field(default_factory=list)
    pending_dumps: list[str] = field(default_factory=list)


def _int(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None


def index_status(session: SyncSession | None, redis: RedisClient | None) -> IndexStatus:
    app_config = config.settings.app_config
    status = IndexStatus(db_file=app_config.fs_index.db_path(app_config.app_data_folder))
    for suffix in ("", "-wal"):
        try:
            status.db_size = (status.db_size or 0) + os.path.getsize(status.db_file + suffix)
        except OSError:
            pass

    if redis is not None:
        try:
            status.running = bool(redis.exists(LOCK_KEY))
            status.queued = int(redis.scard(TOUCH_KEY))  # type: ignore[arg-type]
        except RedisError:
            logger.exception("Failed to read fs-index worker state from Redis")

    meta: dict[str, str | None] = {}
    if session is not None:
        status.available = True
        meta = {key: value for key, value in session.execute(sa.select(Meta.key, Meta.value))}
        if (last_crawl := meta.get("last_crawl")):
            try:
                status.last_crawl = json.loads(last_crawl)
            except ValueError:
                pass
        status.last_change_at = _int(meta.get("last_change_at"))

        now = int(time.time())
        due = sa.text(
            "SELECT COUNT(*) FROM entry WHERE kind = 'd' AND next_check_at IS NOT NULL AND next_check_at <= :until"
        )
        status.due = session.execute(due, {"until": now}).scalar_one()
        status.overdue = session.execute(due, {"until": now - 3600}).scalar_one()

        for root in session.execute(sa.select(Entry).where(Entry.parent_id.is_(None)).order_by(Entry.path)).scalars():
            root_status = RootStatus(root.path, root.total_size or 0, root.n_files or 0)
            root_status.imported_at = _int(meta.get(f"imported_at:{root.path}"))
            root_status.dump_started_at = meta.get(f"dump_started_at:{root.path}")
            if (import_stats := meta.get(f"import_stats:{root.path}")):
                try:
                    root_status.import_seconds = json.loads(import_stats).get("seconds")
                except ValueError:
                    pass
            status.roots.append(root_status)

    # same signature as opengsync_worker.tasks.fs_index_import.pending_dumps
    dump_dir = app_config.fs_index.dump_path(app_config.app_data_folder)
    try:
        names = sorted(name for name in os.listdir(dump_dir) if name.endswith(DUMP_SUFFIX))
    except OSError:
        names = []
    for name in names:
        try:
            st = os.stat(os.path.join(dump_dir, name))
        except OSError:
            continue
        if meta.get(f"dump_file:{name}") != f"{st.st_mtime_ns}:{st.st_size}":
            status.pending_dumps.append(name)
    return status
