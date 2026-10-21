"""Imports the cluster dumps written by `scripts/fs_index_dump.py` into the fs-index.

A dump replaces everything the index holds for its root. Dumps are copied by hand into `dump_dir`; a file is
imported again when its mtime or size changes. All pending dumps go in one transaction and the full-text
index is rebuilt once at the end, so readers keep seeing the previous index until the commit.

    python -m opengsync_worker.tasks.fs_index_import [--config /app/opengsync.yaml]
"""
import gzip
import json
import os
import random
import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from opengsync_db.fs_index import (
    IGNORE_FILENAME, IgnoreRules, connect_writer, create_fts_triggers, drop_fts_triggers, ensure_schema, is_junk,
    rebuild_fts, subtree_bounds,
)

from . import logger
from .fs_index_common import INSERT_ENTRY, FsIndexSettings, contribution, get_meta, set_meta

DUMP_FORMAT = "fs-index-dump"
DUMP_VERSION = 1
DUMP_SUFFIX = ".jsonl.gz"
BATCH_SIZE = 10_000


class InvalidDump(Exception):
    pass


@dataclass
class DumpMeta:
    header: dict
    footer: dict | None = None
    # directory (dump-relative, "" for the root) -> .ngsignore text, None when unreadable
    ignore_files: dict[str, str | None] = field(default_factory=dict)
    error_paths: set[str] = field(default_factory=set)


def _signature(path: str) -> str:
    st = os.stat(path)
    return f"{st.st_mtime_ns}:{st.st_size}"


def pending_dumps(conn: sqlite3.Connection, dump_dir: str) -> list[tuple[str, str]]:
    """(file path, signature) of dumps not imported in their current version."""
    if not os.path.isdir(dump_dir):
        return []
    result = []
    for name in sorted(os.listdir(dump_dir)):
        if not name.endswith(DUMP_SUFFIX):
            continue
        path = os.path.join(dump_dir, name)
        signature = _signature(path)
        if get_meta(conn, f"dump_file:{name}") != signature:
            result.append((path, signature))
    return result


def _share_path(root: str, rel: str) -> str:
    return f"{root}/{rel}" if rel else root


def _encodable(value: str | None) -> bool:
    """Names that were not valid UTF-8 on disk come back with lone surrogates, which SQLite cannot store."""
    if value is None:
        return True
    try:
        value.encode("utf-8")
        return True
    except UnicodeEncodeError:
        return False


def _map_real(real: str | None, roots_real: dict[str, str]) -> str | None:
    """Cluster path a symlink resolves to -> share-root relative path, None when outside all roots."""
    if not real:
        return None
    best = None
    for name, root in roots_real.items():
        if (real == root or real.startswith(root.rstrip("/") + "/")) and (best is None or len(root) > len(best[1])):
            best = (name, root)
    if best is None:
        return None
    name, root = best
    return _share_path(name, real[len(root):].strip("/"))


def _epoch(iso: str | None) -> float | None:
    try:
        return datetime.fromisoformat(iso).timestamp() if iso else None
    except ValueError:
        return None


def scan_meta(path: str) -> DumpMeta:
    """First pass: header, footer, `.ngsignore` contents and errors (all JSON objects, entries are arrays)."""
    meta: DumpMeta | None = None
    with gzip.open(path, "rb") as f:
        for i, line in enumerate(f):
            if line[:1] != b"{":
                continue
            record = json.loads(line)
            kind = record.get("kind")
            if i == 0 and kind == "header":
                meta = DumpMeta(header=record)
            elif meta is None:
                raise InvalidDump(f"{path}: first line is not a header")
            elif kind == "footer":
                meta.footer = record
            elif kind == "ignore":
                meta.ignore_files[record["path"].rpartition("/")[0]] = record["content"]
            elif kind == "error":
                directory, _, name = record["path"].rpartition("/")
                if name == IGNORE_FILENAME:
                    meta.ignore_files[directory] = None
                else:
                    meta.error_paths.add(record["path"])
    if meta is None:
        raise InvalidDump(f"{path}: empty")
    if meta.header.get("format") != DUMP_FORMAT or meta.header.get("version") != DUMP_VERSION:
        raise InvalidDump(f"{path}: unsupported format {meta.header.get('format')} v{meta.header.get('version')}")
    if meta.footer is None:
        raise InvalidDump(f"{path}: no footer, the dump is incomplete")
    return meta


def import_dump(conn: sqlite3.Connection, path: str, settings: FsIndexSettings, now: int) -> dict:
    """Replaces the root's rows with the dump's. Runs inside the caller's transaction, FTS triggers dropped."""
    meta = scan_meta(path)
    root = meta.header["name"]
    roots_real = meta.header.get("roots_real") or {}
    rules = IgnoreRules({_share_path(root, d): content for d, content in meta.ignore_files.items()})

    lower, upper = subtree_bounds(root)
    conn.execute("DELETE FROM entry WHERE path = ? OR (path >= ? AND path < ?)", (root, lower, upper))
    conn.execute("DELETE FROM ignore_file WHERE dir_path = ? OR (dir_path >= ? AND dir_path < ?)", (root, lower, upper))

    next_id = (conn.execute("SELECT MAX(id) FROM entry").fetchone()[0] or 0) + 1
    dir_ids: dict[str, int] = {}
    # id -> (path, mtime, hidden, opaque, parent id) of every inserted directory
    dirs: dict[int, tuple[str, int | None, bool, bool, int | None]] = {}
    # id -> [bytes, files, max mtime] from direct children; child directories are added bottom-up at the end
    acc: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0])
    # directory path -> its opaque ancestor-or-self, or None
    opaque_of: dict[str, str | None] = {root: None}

    def dir_id(p: str) -> int:
        nonlocal next_id
        if (i := dir_ids.get(p)) is None:
            i = dir_ids[p] = next_id
            next_id += 1
        return i

    def opaque_ancestor(directory: str) -> str | None:
        if directory in opaque_of:
            return opaque_of[directory]
        parent, _, name = directory.rpartition("/")
        result = opaque_ancestor(parent) or (directory if settings.is_index_ignored(name) else None)
        opaque_of[directory] = result
        return result

    root_id = dir_id(root)
    rows: list[tuple] = [(
        root_id, root, None, root, "d", None, meta.header.get("root_mtime"), None, None, None,
        False, False, True, False, None, None, None, None, None,
    )]
    dirs[root_id] = (root, meta.header.get("root_mtime"), False, False, None)
    stats = {"entries": 0, "skipped": 0}

    def flush():
        conn.executemany(INSERT_ENTRY, rows)
        rows.clear()

    with gzip.open(path, "rb") as f:
        for line in f:
            if line[:1] != b"[":
                continue
            record = json.loads(line)
            rel, kind, size, mtime = record[0], record[1], record[2], record[3]
            if kind not in ("d", "f", "l") or not rel or not _encodable(rel):
                stats["skipped"] += 1
                continue
            entry_path = _share_path(root, rel)
            if is_junk(entry_path):
                stats["skipped"] += 1
                continue

            parent, _, name = entry_path.rpartition("/")
            link_target = target_kind = target_size = None
            if kind == "l":
                target_kind, target_size = record[6], record[7]
                link_target = _map_real(record[5], roots_real)
                if not _encodable(link_target):
                    link_target = None
            unsafe = kind == "l" and link_target is None
            hidden = rules.is_hidden(entry_path, kind == "d", link_target)

            opaque_dir = opaque_ancestor(parent)
            owner_id = dir_id(opaque_dir or parent)
            if not hidden:
                if kind == "d":
                    if opaque_dir is not None:
                        acc[owner_id][2] = max(acc[owner_id][2], mtime or 0)
                else:
                    add_size, add_files = contribution(kind, size, target_kind, target_size, None, None, hidden, unsafe)
                    owner = acc[owner_id]
                    owner[0] += add_size
                    owner[1] += add_files
                    owner[2] = max(owner[2], mtime or 0)
            if opaque_dir is not None:
                continue

            if kind == "d":
                entry_id = dir_id(entry_path)
                opaque = settings.is_index_ignored(name)
                dirs[entry_id] = (entry_path, mtime, hidden, opaque, owner_id)
            else:
                entry_id = next_id
                next_id += 1
                opaque = False
            rows.append((
                entry_id, entry_path, owner_id, name, kind, size, mtime, link_target, target_kind, target_size,
                hidden, unsafe, not opaque, opaque, None, None, None, None, None,
            ))
            stats["entries"] += 1
            if len(rows) >= BATCH_SIZE:
                flush()
    flush()

    # deepest first, so a directory is complete before it is added to its parent
    updates = []
    for entry_id, (entry_path, mtime, hidden, opaque, parent_id) in sorted(
        dirs.items(), key=lambda item: item[1][0].count("/"), reverse=True,
    ):
        size, files, max_mtime = acc.get(entry_id, (0, 0, 0))
        max_mtime = max(max_mtime, mtime or 0)
        if hidden:
            size, files = 0, 0
        elif parent_id is not None:
            parent = acc[parent_id]
            parent[0] += size
            parent[1] += files
            parent[2] = max(parent[2], max_mtime)

        interval = settings.seed_interval(now - max_mtime)
        next_check_at = None if opaque else now + random.randint(0, interval)
        updates.append((size, files, max_mtime, next_check_at, interval, entry_id))
    conn.executemany(
        "UPDATE entry SET total_size = ?, n_files = ?, max_mtime = ?, next_check_at = ?, check_interval = ? WHERE id = ?",
        updates,
    )

    # directories the dump could not list are listed by the crawler first
    conn.executemany(
        "UPDATE entry SET mtime = NULL, next_check_at = ? WHERE path = ? AND kind = 'd' AND NOT opaque",
        [(now, _share_path(root, rel)) for rel in meta.error_paths if _encodable(rel)],
    )
    # a directory that changed while the dump ran may have changed after it was listed (mtimes have 1 s
    # resolution): stored as not listed, so the crawler lists it on its first check
    if (started := _epoch(meta.header.get("started_at"))) is not None:
        lower, upper = subtree_bounds(root)
        conn.execute(
            "UPDATE entry SET mtime = NULL WHERE (path = ? OR (path >= ? AND path < ?)) AND kind = 'd' "
            "AND NOT opaque AND mtime >= ?",
            (root, lower, upper, int(started) - 1),
        )
    conn.executemany(
        "INSERT INTO ignore_file (dir_path, content) VALUES (?, ?)",
        [(_share_path(root, d), content) for d, content in meta.ignore_files.items() if _encodable(d)],
    )

    set_meta(conn, f"imported_at:{root}", str(now))
    set_meta(conn, f"dump_started_at:{root}", meta.header.get("started_at"))
    stats["root"] = root
    stats["errors"] = len(meta.error_paths)
    return stats


def import_dumps(settings: FsIndexSettings, now: int | None = None) -> list[dict]:
    """Imports every new or changed dump in `settings.dump_dir`; returns one stats dict per imported dump."""
    now = int(now if now is not None else time.time())
    ensure_schema(settings.db_file)
    conn = connect_writer(settings.db_file)
    try:
        pending = pending_dumps(conn, settings.dump_dir)
        if not pending:
            return []

        imported = []
        conn.execute("BEGIN IMMEDIATE")
        try:
            drop_fts_triggers(conn)
            for path, signature in pending:
                file_name = os.path.basename(path)
                conn.execute("SAVEPOINT dump")
                try:
                    started = time.monotonic()
                    stats = import_dump(conn, path, settings, now)
                    stats["seconds"] = round(time.monotonic() - started, 1)
                    stats["file"] = file_name
                    set_meta(conn, f"import_stats:{stats['root']}", json.dumps(stats))
                    conn.execute("RELEASE dump")
                    imported.append(stats)
                    logger.info(f"fs-index: imported {file_name}: {stats}")
                except (InvalidDump, OSError, EOFError, ValueError, KeyError, IndexError) as e:
                    conn.execute("ROLLBACK TO dump")
                    conn.execute("RELEASE dump")
                    logger.error(f"fs-index: skipping {file_name}: {e!r}")
                # a broken file is not retried until it is replaced
                set_meta(conn, f"dump_file:{file_name}", signature)
            create_fts_triggers(conn)
            rebuild_fts(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        return imported
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    import yaml

    parser = argparse.ArgumentParser(description="Import fs-index dumps")
    parser.add_argument("--config", default="/app/opengsync.yaml")
    args = parser.parse_args()
    with open(args.config) as f:
        for stats in import_dumps(FsIndexSettings.from_config(yaml.safe_load(f))):
            print(stats)
