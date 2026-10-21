"""Keeps the fs-index current by re-listing only directories whose mtime changed.

Each directory has its own check interval: it resets to `min_interval_s` when the directory changed and
doubles up to `max_interval_s` while it doesn't, so finished data is rarely looked at. A directory's mtime
only changes for direct children, so every non-opaque directory is checked on its own schedule.

The share is a network mount: a root whose mount is down looks empty or missing, so nothing is deleted
under a root that fails its online check.
"""
import errno
import json
import os
import sqlite3
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from opengsync_db.fs_index import (
    IGNORE_FILENAME, IgnoreRules, connect_writer, ensure_schema, is_junk, parent_path,
)

from . import logger
from .fs_index_common import (
    INSERT_ENTRY, FsIndexSettings, add_to_ancestors, contribution, delete_subtree, load_ignore_rules,
    recompute_subtree, set_meta,
)

MAX_IGNORE_FILE_SIZE = 1024 * 1024
# mtimes have 1 s resolution (all sshfs offers): a directory changed in the second it was listed may have
# changed after the listing, so it is stored as not listed and listed again on its next check
RACY_S = 1
# listing this many entries costs as much of the rate limit as checking one more folder
ENTRIES_PER_RATE_UNIT = 200
# a directory row as the crawler reads it
DIR_COLUMNS = "id, path, mtime, check_interval, hidden, total_size, n_files"


class RateLimiter:
    """Spaces filesystem work out to `per_second` units across all threads, so the crawler never bursts
    against the share's (network) metadata server, however much is due."""

    def __init__(self, per_second: float):
        self.interval = 1 / per_second if per_second > 0 else 0.0
        self._next = time.monotonic()
        self._lock = threading.Lock()

    def wait(self, units: float = 1) -> None:
        if not self.interval or units <= 0:
            return
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + units * self.interval
        if start > now:
            time.sleep(start - now)


@dataclass
class DirRow:
    id: int
    path: str
    mtime: int | None
    check_interval: int | None
    hidden: bool
    total_size: int | None
    n_files: int | None


@dataclass
class Child:
    name: str
    kind: str
    size: int | None
    mtime: int
    link_target: str | None = None
    target_kind: str | None = None
    target_size: int | None = None


_ABSENT = object()


@dataclass
class Probe:
    # "same": mtime unchanged, "changed": listed, "gone": no longer a directory, "error": could not stat/list
    status: str
    mtime: int | None = None
    children: list[Child] | None = None
    # .ngsignore text, None when unreadable, _ABSENT when there is none
    ignore: object = _ABSENT
    error: str | None = None
    # wall-clock time just before the listing
    listed_at: float = 0.0


class Crawler:
    def __init__(self, conn: sqlite3.Connection, settings: FsIndexSettings, now: float | None = None):
        self.conn = conn
        self.settings = settings
        self.share_root = os.path.realpath(settings.share_root)
        self._now = now
        self.rules: IgnoreRules = load_ignore_rules(conn)
        self.online: dict[str, bool] = {}
        self.limiter = RateLimiter(settings.crawl_rate)
        self.stats = {"checked": 0, "changed": 0, "gone": 0, "errors": 0, "added": 0, "removed": 0}

    def now(self) -> int:
        return int(self._now if self._now is not None else time.time())

    # ── filesystem (runs in worker threads) ──────────────────────

    def _full(self, path: str) -> str:
        return os.path.join(self.share_root, path)

    def _share_relative(self, real: str) -> str | None:
        if real.startswith(self.share_root + os.sep):
            return real[len(self.share_root) + 1:].replace(os.sep, "/")
        return None

    def _child(self, entry: os.DirEntry) -> Child | None:
        st = entry.stat(follow_symlinks=False)
        if stat.S_ISDIR(st.st_mode):
            return Child(entry.name, "d", None, int(st.st_mtime))
        if stat.S_ISREG(st.st_mode):
            return Child(entry.name, "f", st.st_size, int(st.st_mtime))
        if not stat.S_ISLNK(st.st_mode):
            return None
        child = Child(entry.name, "l", st.st_size, int(st.st_mtime))
        child.link_target = self._share_relative(os.path.realpath(entry.path))
        try:
            target = os.stat(entry.path)
        except OSError as e:
            child.target_kind = "loop" if e.errno == errno.ELOOP else "missing"
            return child
        if stat.S_ISDIR(target.st_mode):
            child.target_kind = "d"
        elif stat.S_ISREG(target.st_mode):
            child.target_kind, child.target_size = "f", target.st_size
        else:
            child.target_kind = "o"
        return child

    def _read_ignore(self, path: str) -> str | None:
        try:
            if os.path.getsize(path) > MAX_IGNORE_FILE_SIZE:
                return None
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return None

    def probe(self, row: DirRow) -> Probe:
        self.limiter.wait()
        full = self._full(row.path)
        try:
            st = os.lstat(full)
        except (FileNotFoundError, NotADirectoryError):
            return Probe("gone")
        except OSError as e:
            return Probe("error", error=repr(e))
        if not stat.S_ISDIR(st.st_mode):
            return Probe("gone")
        mtime = int(st.st_mtime)
        if row.mtime == mtime:
            return Probe("same", mtime=mtime)

        children: list[Child] = []
        ignore: object = _ABSENT
        listed_at = time.time()
        try:
            with os.scandir(full) as it:
                for entry in it:
                    try:
                        child = self._child(entry)
                    except OSError:
                        continue
                    if child is None:
                        continue
                    children.append(child)
                    if child.name == IGNORE_FILENAME and child.kind == "f":
                        ignore = self._read_ignore(entry.path)
        except OSError as e:
            return Probe("error", error=repr(e))
        # a big listing (and its per-entry stats) pays for itself before the next check starts
        self.limiter.wait(len(children) / ENTRIES_PER_RATE_UNIT)
        return Probe("changed", mtime=mtime, children=children, ignore=ignore, listed_at=listed_at)

    def is_online(self, path: str) -> bool:
        """A root's mount is up: its canary file exists, or (without one) it has any entries."""
        root = path.split("/", 1)[0]
        if (online := self.online.get(root)) is None:
            canary = self.settings.canaries.get(root)
            try:
                if canary is not None:
                    online = os.path.isfile(self._full(canary))
                else:
                    with os.scandir(self._full(root)) as it:
                        online = next(it, None) is not None
            except OSError:
                online = False
            self.online[root] = online
            if not online:
                logger.warning(f"fs-index: {root} looks offline, not removing anything under it")
        return online

    # ── index updates (main thread, inside a transaction) ────────

    def _dir_row(self, row_id: int) -> DirRow | None:
        row = self.conn.execute(f"SELECT {DIR_COLUMNS} FROM entry WHERE id = ?", (row_id,)).fetchone()
        return DirRow(*row) if row else None

    def _backoff(self, row: DirRow) -> None:
        interval = min(max(row.check_interval or 0, self.settings.min_interval_s) * 2, self.settings.max_interval_s)
        self.conn.execute(
            "UPDATE entry SET check_interval = ?, next_check_at = ? WHERE id = ?",
            (interval, self.now() + interval, row.id),
        )

    def _remove_dir(self, row: DirRow) -> None:
        delete_subtree(self.conn, row.path)
        if not row.hidden:
            add_to_ancestors(self.conn, row.path, -(row.total_size or 0), -(row.n_files or 0), None)
        self.stats["removed"] += 1

    def _remove_child(self, path: str, kind: str) -> None:
        """The parent's totals are rebuilt from its remaining children afterwards."""
        if kind == "d":
            delete_subtree(self.conn, path)
        else:
            self.conn.execute("DELETE FROM entry WHERE path = ?", (path,))
        self.stats["removed"] += 1

    def _insert(self, parent: DirRow, child: Child) -> None:
        path = f"{parent.path}/{child.name}"
        hidden = self.rules.is_hidden(path, child.kind == "d", child.link_target)
        unsafe = child.kind == "l" and child.link_target is None
        if child.kind == "d":
            opaque = self.settings.is_index_ignored(child.name)
            # never listed: mtime stays NULL until the crawler lists it, which is due right away
            values = (
                None, path, parent.id, child.name, "d", None, None, None, None, None,
                hidden, False, not opaque, opaque, 0, 0, child.mtime,
                None if opaque else self.now(), self.settings.min_interval_s,
            )
        else:
            values = (
                None, path, parent.id, child.name, child.kind, child.size, child.mtime,
                child.link_target, child.target_kind, child.target_size,
                hidden, unsafe, True, False, None, None, None, None, None,
            )
        self.conn.execute(INSERT_ENTRY, values)
        self.stats["added"] += 1

    def _apply_ignore(self, row: DirRow, ignore: object) -> bool:
        """Stores the directory's .ngsignore; True when it changed."""
        stored = self.conn.execute("SELECT content FROM ignore_file WHERE dir_path = ?", (row.path,)).fetchone()
        old = _ABSENT if stored is None else stored[0]
        if old == ignore:
            return False
        if ignore is _ABSENT:
            self.conn.execute("DELETE FROM ignore_file WHERE dir_path = ?", (row.path,))
        else:
            self.conn.execute(
                "INSERT INTO ignore_file (dir_path, content) VALUES (?, ?) "
                "ON CONFLICT(dir_path) DO UPDATE SET content = excluded.content",
                (row.path, ignore),
            )
        self.rules = load_ignore_rules(self.conn)
        return True

    def _refresh_totals(self, row: DirRow) -> None:
        """Rebuilds the directory's totals from its children and moves its ancestors by the difference."""
        size = files = 0
        max_mtime = row.mtime or 0
        for kind, c_size, c_mtime, target_kind, target_size, hidden, unsafe, total, n, c_max in self.conn.execute(
            "SELECT kind, size, mtime, target_kind, target_size, hidden, unsafe, total_size, n_files, max_mtime "
            "FROM entry WHERE parent_id = ?", (row.id,),
        ):
            add_size, add_files = contribution(kind, c_size, target_kind, target_size, total, n, hidden, unsafe)
            size += add_size
            files += add_files
            if not hidden:
                max_mtime = max(max_mtime, (c_max if kind == "d" else c_mtime) or 0)
        if row.hidden:
            size = files = 0
        self.conn.execute(
            "UPDATE entry SET total_size = ?, n_files = ?, max_mtime = ? WHERE id = ?",
            (size, files, max_mtime, row.id),
        )
        if not row.hidden:
            add_to_ancestors(self.conn, row.path, size - (row.total_size or 0), files - (row.n_files or 0), max_mtime)

    def apply(self, row: DirRow, probe: Probe) -> None:
        self.stats["checked"] += 1
        if probe.status == "error":
            self.stats["errors"] += 1
            logger.warning(f"fs-index: cannot check {row.path}: {probe.error}")
            self._backoff(row)
            return
        if probe.status == "gone":
            if not self.is_online(row.path):
                self._backoff(row)
                return
            self.stats["gone"] += 1
            self._remove_dir(row)
            return
        if probe.status == "same":
            self._backoff(row)
            return

        self.stats["changed"] += 1
        assert probe.children is not None
        existing = {
            r[0]: r for r in self.conn.execute(
                "SELECT name, kind, size, mtime, link_target, target_kind, target_size "
                "FROM entry WHERE parent_id = ?", (row.id,),
            )
        }
        current = {c.name: c for c in probe.children if not is_junk(f"{row.path}/{c.name}")}
        if any(name not in current for name in existing) and not self.is_online(row.path):
            self._backoff(row)
            return

        rules_changed = self._apply_ignore(row, probe.ignore)
        for name, e in existing.items():
            child = current.get(name)
            if child is None or child.kind != e[1]:
                self._remove_child(f"{row.path}/{name}", e[1])
        for name, child in current.items():
            e = existing.get(name)
            if e is None or child.kind != e[1]:
                self._insert(row, child)
            elif child.kind != "d" and (child.size, child.mtime, child.link_target, child.target_kind, child.target_size) != e[2:7]:
                # a directory's own mtime is compared when the crawler visits it
                path = f"{row.path}/{name}"
                hidden = self.rules.is_hidden(path, False, child.link_target)
                self.conn.execute(
                    "UPDATE entry SET size = ?, mtime = ?, link_target = ?, target_kind = ?, target_size = ?, "
                    "hidden = ?, unsafe = ? WHERE path = ?",
                    (child.size, child.mtime, child.link_target, child.target_kind, child.target_size,
                     hidden, child.kind == "l" and child.link_target is None, path),
                )

        racy = probe.mtime is not None and probe.mtime >= probe.listed_at - RACY_S
        self.conn.execute(
            "UPDATE entry SET mtime = ?, check_interval = ?, next_check_at = ? WHERE id = ?",
            (None if racy else probe.mtime, self.settings.min_interval_s,
             self.now() + self.settings.min_interval_s, row.id),
        )
        row.mtime = probe.mtime
        if rules_changed:
            recompute_subtree(self.conn, row.path, self.rules)
        else:
            self._refresh_totals(row)

    # ── scheduling ───────────────────────────────────────────────

    def ensure_roots(self) -> None:
        """Adds share roots the index does not know yet (they get listed by the crawler, no dump needed)."""
        try:
            names = [e.name for e in os.scandir(self.share_root) if e.is_dir()]
        except OSError as e:
            logger.warning(f"fs-index: cannot list {self.share_root}: {e!r}")
            return
        for name in names:
            if self.conn.execute("SELECT 1 FROM entry WHERE path = ?", (name,)).fetchone() is None:
                self.conn.execute(INSERT_ENTRY, (
                    None, name, None, name, "d", None, None, None, None, None,
                    False, False, True, False, 0, 0, None, self.now(), self.settings.min_interval_s,
                ))

    def touch(self, paths: list[str]) -> None:
        """Makes these directories due now. For a path the index doesn't know, its nearest known ancestor is
        listed again, which discovers it."""
        for path in paths:
            path = path.strip("/")
            force_list = False
            while path:
                row = self.conn.execute(
                    "SELECT id FROM entry WHERE path = ? AND kind = 'd' AND NOT opaque", (path,),
                ).fetchone()
                if row is not None:
                    self.conn.execute(
                        f"UPDATE entry SET next_check_at = ?{', mtime = NULL' if force_list else ''} WHERE id = ?",
                        (self.now(), row[0]),
                    )
                    break
                path = parent_path(path) or ""
                force_list = True

    def due(self, limit: int) -> list[DirRow]:
        rows = self.conn.execute(
            f"SELECT {DIR_COLUMNS} FROM entry WHERE kind = 'd' AND next_check_at IS NOT NULL AND next_check_at <= ? "
            "ORDER BY next_check_at LIMIT ?",
            (self.now(), limit),
        ).fetchall()
        return [DirRow(*row) for row in rows]

    def check_ignore_files(self) -> None:
        """An edited .ngsignore does not change its directory's mtime, so they are checked on every run."""
        for (directory,) in self.conn.execute("SELECT dir_path FROM ignore_file").fetchall():
            path = f"{directory}/{IGNORE_FILENAME}"
            stored = self.conn.execute("SELECT size, mtime FROM entry WHERE path = ?", (path,)).fetchone()
            try:
                st = os.lstat(self._full(path))
                current = (st.st_size, int(st.st_mtime))
            except OSError:
                current = None
            if stored is None or current != tuple(stored):
                self.conn.execute(
                    "UPDATE entry SET mtime = NULL, next_check_at = ? WHERE path = ? AND kind = 'd'",
                    (self.now(), directory),
                )


def crawl(settings: FsIndexSettings, touched: list[str] | None = None, now: float | None = None) -> dict:
    """One budgeted crawl run. `touched`: directories the app just listed live, checked first."""
    ensure_schema(settings.db_file)
    conn = connect_writer(settings.db_file)
    started = time.monotonic()
    try:
        crawler = Crawler(conn, settings, now=now)
        conn.execute("BEGIN IMMEDIATE")
        crawler.ensure_roots()
        crawler.check_ignore_files()
        crawler.touch(touched or [])
        conn.execute("COMMIT")

        with ThreadPoolExecutor(max_workers=max(1, settings.crawl_threads)) as pool:
            while (remaining := settings.crawl_budget_s - (time.monotonic() - started)) > 0:
                # with a rate limit, no more than fits in the time left, so a run ends near its budget
                batch = settings.crawl_batch
                if settings.crawl_rate > 0:
                    batch = max(1, min(batch, int(remaining * settings.crawl_rate)))
                rows = crawler.due(batch)
                if not rows:
                    break
                probes = list(pool.map(crawler.probe, rows))
                conn.execute("BEGIN IMMEDIATE")
                try:
                    for row, probe in zip(rows, probes):
                        # an earlier row of this batch may have removed or changed it
                        current = crawler._dir_row(row.id)
                        if current is None:
                            continue
                        if current.mtime != row.mtime:
                            probe = crawler.probe(current)
                        crawler.apply(current, probe)
                    set_meta(conn, "crawled_at", str(crawler.now()))
                    conn.execute("COMMIT")
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
        crawler.stats["seconds"] = round(time.monotonic() - started, 1)
        crawler.stats["at"] = crawler.now()
        # shown on the insider dashboard (server/utils/fs_index.py)
        conn.execute("BEGIN IMMEDIATE")
        set_meta(conn, "last_crawl", json.dumps(crawler.stats))
        if crawler.stats["added"] or crawler.stats["removed"] or crawler.stats["changed"]:
            set_meta(conn, "last_change_at", str(crawler.now()))
        conn.execute("COMMIT")
        return crawler.stats
    finally:
        conn.close()
