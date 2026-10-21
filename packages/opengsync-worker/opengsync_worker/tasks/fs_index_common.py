"""Shared by the fs-index import and crawl tasks: settings and the write helpers that keep totals consistent."""
import fnmatch
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from opengsync_db.fs_index import IgnoreRules, ancestor_paths, subtree_bounds

DAY_S = 24 * 3600

# Pipeline internals and temp folders: their directory is stored (with its totals) but nothing below it,
# and they are left out of search.
DEFAULT_INDEX_IGNORE = (
    "*_CS",            # Cell Ranger / Space Ranger (martian) pipeline internals
    "chnk*",
    "work",            # Nextflow
    ".nextflow",
    ".snakemake",
    "Rtmp*",           # R session temp
    "*_temporary",
    "BaseCalls",       # Illumina run folder internals
)

ENTRY_COLUMNS = (
    "id", "path", "parent_id", "name", "kind", "size", "mtime", "link_target", "target_kind", "target_size",
    "hidden", "unsafe", "searchable", "opaque", "total_size", "n_files", "max_mtime", "next_check_at", "check_interval",
)
INSERT_ENTRY = f"INSERT INTO entry ({', '.join(ENTRY_COLUMNS)}) VALUES ({', '.join('?' * len(ENTRY_COLUMNS))})"


@dataclass
class FsIndexSettings:
    db_file: str
    dump_dir: str
    share_root: str
    min_interval_s: int = 120
    max_interval_s: int = 7 * DAY_S
    crawl_budget_s: int = 50
    crawl_batch: int = 500
    # folders checked at a time; 1 is gentlest on the share
    crawl_threads: int = 1
    # folders checked per second, all threads together; listing a big folder counts as more (0: no limit)
    crawl_rate: float = 10
    index_ignore: tuple[str, ...] = DEFAULT_INDEX_IGNORE
    # share-root relative files that only exist while the root's mount is up (from `canary_files`)
    canaries: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: dict) -> "FsIndexSettings":
        """`config` is the raw opengsync.yaml dict; the `fs_index` section is optional."""
        section = config.get("fs_index") or {}
        app_data = config.get("app_data_folder", "/app_data")
        share_root = config["share_root"]

        canaries: dict[str, str] = {}
        for canary in (config.get("canary_files") or {}).values():
            try:
                rel = Path(canary).relative_to(share_root).as_posix()
            except ValueError:
                continue
            canaries[rel.split("/", 1)[0]] = rel

        kwargs = {
            key: section[key] for key in (
                "min_interval_s", "max_interval_s", "crawl_budget_s", "crawl_batch", "crawl_threads", "crawl_rate",
            ) if section.get(key) is not None
        }
        if section.get("index_ignore") is not None:
            kwargs["index_ignore"] = tuple(section["index_ignore"])
        return cls(
            db_file=section.get("db_file") or os.path.join(app_data, "fs_index", "fs_index.sqlite3"),
            dump_dir=section.get("dump_dir") or os.path.join(app_data, "fs_index", "dumps"),
            share_root=share_root,
            canaries=canaries,
            **kwargs,
        )

    def is_index_ignored(self, name: str) -> bool:
        return any(fnmatch.fnmatchcase(name, pattern) for pattern in self.index_ignore)

    def seed_interval(self, age_s: float) -> int:
        """Check interval for a directory whose subtree last changed `age_s` ago."""
        if age_s < 7 * DAY_S:
            return self.min_interval_s
        if age_s < 90 * DAY_S:
            return min(6 * 3600, self.max_interval_s)
        return self.max_interval_s


def contribution(
    kind: str, size: int | None, target_kind: str | None, target_size: int | None,
    total_size: int | None, n_files: int | None, hidden: bool, unsafe: bool,
) -> tuple[int, int]:
    """(bytes, files) an entry adds to its parent's totals: what a share link of the parent would serve.

    Symlinks to directories count as nothing: their target is counted under its own path.
    """
    if hidden or unsafe:
        return 0, 0
    if kind == "f":
        return size or 0, 1
    if kind == "l" and target_kind == "f":
        return target_size or 0, 1
    if kind == "d":
        return total_size or 0, n_files or 0
    return 0, 0


def add_to_ancestors(conn: sqlite3.Connection, path: str, d_size: int, d_files: int, mtime: int | None) -> None:
    paths = ancestor_paths(path)
    if not paths or (not d_size and not d_files and mtime is None):
        return
    placeholders = ", ".join("?" * len(paths))
    conn.execute(
        "UPDATE entry SET total_size = COALESCE(total_size, 0) + ?, n_files = COALESCE(n_files, 0) + ?, "
        f"max_mtime = MAX(COALESCE(max_mtime, 0), ?) WHERE path IN ({placeholders})",
        (d_size, d_files, mtime or 0, *paths),
    )


def delete_subtree(conn: sqlite3.Connection, path: str) -> None:
    lower, upper = subtree_bounds(path)
    conn.execute("DELETE FROM entry WHERE path = ? OR (path >= ? AND path < ?)", (path, lower, upper))
    conn.execute("DELETE FROM ignore_file WHERE dir_path = ? OR (dir_path >= ? AND dir_path < ?)", (path, lower, upper))


def load_ignore_rules(conn: sqlite3.Connection) -> IgnoreRules:
    return IgnoreRules(dict(conn.execute("SELECT dir_path, content FROM ignore_file").fetchall()))


def recompute_subtree(conn: sqlite3.Connection, path: str, rules: IgnoreRules) -> None:
    """Re-evaluates hidden flags below `path` and rebuilds its totals, then moves its ancestors by the difference.

    Used when a `.ngsignore` in `path` changed. The flag of `path` itself depends only on its parents' rules.
    Opaque directories keep their stored totals (their children are not in the index).
    """
    lower, upper = subtree_bounds(path)
    rows = conn.execute(
        "SELECT id, path, parent_id, kind, size, mtime, link_target, target_kind, target_size, hidden, unsafe, "
        "opaque, total_size, n_files, max_mtime FROM entry WHERE path = ? OR (path >= ? AND path < ?)",
        (path, lower, upper),
    ).fetchall()
    if not rows:
        return

    top = next(row for row in rows if row[1] == path)
    by_id = {row[0]: row for row in rows}
    hidden = {row[0]: bool(row[9]) for row in rows}
    for row in rows:
        if row[0] != top[0]:
            hidden[row[0]] = rules.is_hidden(row[1], row[3] == "d", row[6])

    acc: dict[int, list[int]] = {row[0]: [0, 0, row[5] or 0] for row in rows if row[3] == "d"}
    # deepest first, so a directory is complete before it is added to its parent
    for row in sorted(rows, key=lambda r: r[1].count("/"), reverse=True):
        row_id, parent_id, kind = row[0], row[2], row[3]
        if kind == "d":
            if row[11]:  # opaque
                acc[row_id] = [row[12] or 0, row[13] or 0, row[14] or row[5] or 0]
            elif hidden[row_id]:
                acc[row_id] = [0, 0, row[5] or 0]
        if row_id == top[0] or parent_id not in acc:
            continue
        if kind == "d":
            size, files = (0, 0) if hidden[row_id] else (acc[row_id][0], acc[row_id][1])
            mtime = acc[row_id][2]
        else:
            size, files = contribution(kind, row[4], row[7], row[8], None, None, hidden[row_id], bool(row[10]))
            mtime = row[5] or 0
        parent = acc[parent_id]
        parent[0] += size
        parent[1] += files
        if not hidden[row_id]:
            parent[2] = max(parent[2], mtime)

    conn.executemany(
        "UPDATE entry SET hidden = ? WHERE id = ?",
        [(hidden[row[0]], row[0]) for row in rows if bool(row[9]) != hidden[row[0]]],
    )
    conn.executemany(
        "UPDATE entry SET total_size = ?, n_files = ?, max_mtime = ? WHERE id = ?",
        [(a[0], a[1], a[2], row_id) for row_id, a in acc.items() if not by_id[row_id][11]],
    )
    old_size, old_files = top[12] or 0, top[13] or 0
    new_size, new_files, new_mtime = acc[top[0]] if top[3] == "d" else (0, 0, None)
    if not top[9]:
        add_to_ancestors(conn, path, new_size - old_size, new_files - old_files, new_mtime)


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
