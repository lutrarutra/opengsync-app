import os
import sqlite3
from collections.abc import Iterable

import sqlalchemy as sa

from .models import FsIndexBase

# Bump on any schema change: the index is a cache, so a mismatching file is deleted and rebuilt.
SCHEMA_VERSION = 1
MIN_SQLITE_VERSION = (3, 34, 0)  # fts5 trigram tokenizer

FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS entry_fts USING fts5(name, content='entry', content_rowid='id', tokenize='trigram')",
)

TRIGGERS = {
    "entry_fts_ai": "CREATE TRIGGER IF NOT EXISTS entry_fts_ai AFTER INSERT ON entry BEGIN "
                    "INSERT INTO entry_fts(rowid, name) VALUES (new.id, new.name); END",
    "entry_fts_ad": "CREATE TRIGGER IF NOT EXISTS entry_fts_ad AFTER DELETE ON entry BEGIN "
                    "INSERT INTO entry_fts(entry_fts, rowid, name) VALUES ('delete', old.id, old.name); END",
    "entry_fts_au": "CREATE TRIGGER IF NOT EXISTS entry_fts_au AFTER UPDATE OF name ON entry BEGIN "
                    "INSERT INTO entry_fts(entry_fts, rowid, name) VALUES ('delete', old.id, old.name); "
                    "INSERT INTO entry_fts(rowid, name) VALUES (new.id, new.name); END",
}


def check_sqlite_version() -> None:
    if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
        raise RuntimeError(
            f"fs-index needs SQLite >= {'.'.join(map(str, MIN_SQLITE_VERSION))}, found {sqlite3.sqlite_version}"
        )


def subtree_bounds(path: str) -> tuple[str, str]:
    """Strict descendants of `path` are `lower <= p < upper` ('0' sorts right after '/')."""
    return path + "/", path + "0"


def parent_path(path: str) -> str | None:
    parent, sep, _ = path.rpartition("/")
    return parent if sep else None


def ancestor_paths(path: str) -> list[str]:
    """Nearest first, the root entry (e.g. "BSF_PROJECTS") last."""
    parts = path.split("/")
    return ["/".join(parts[:i]) for i in range(len(parts) - 1, 0, -1)]


def drop_fts_triggers(conn: sqlite3.Connection) -> None:
    for name in TRIGGERS:
        conn.execute(f"DROP TRIGGER IF EXISTS {name}")


def create_fts_triggers(conn: sqlite3.Connection) -> None:
    for ddl in TRIGGERS.values():
        conn.execute(ddl)


def rebuild_fts(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO entry_fts(entry_fts) VALUES ('rebuild')")


def _exec_all(conn: sa.Connection, statements: Iterable[str]) -> None:
    for statement in statements:
        conn.exec_driver_sql(statement)


def ensure_schema(db_file: str) -> None:
    """Creates the index file, or deletes and recreates it when its schema version differs (writer only)."""
    check_sqlite_version()
    os.makedirs(os.path.dirname(os.path.abspath(db_file)), exist_ok=True)

    if os.path.exists(db_file):
        with sqlite3.connect(db_file) as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.close()
        if version == SCHEMA_VERSION:
            return
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(db_file + suffix)
            except FileNotFoundError:
                pass

    engine = sa.create_engine(f"sqlite:///{db_file}")
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            FsIndexBase.metadata.create_all(conn)
            _exec_all(conn, FTS_DDL)
            _exec_all(conn, TRIGGERS.values())
            conn.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
    finally:
        engine.dispose()


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]
