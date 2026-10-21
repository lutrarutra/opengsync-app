import os
import sqlite3
import threading

import sqlalchemy as sa
from sqlalchemy import event, orm

from ..core.SyncSession import SyncSession
from .schema import SCHEMA_VERSION, check_sqlite_version

BUSY_TIMEOUT_MS = 5000


def connect_writer(db_file: str) -> sqlite3.Connection:
    """Raw connection for the single writer (the worker), in autocommit mode: callers BEGIN/COMMIT explicitly."""
    conn = sqlite3.connect(db_file, isolation_level=None, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-65536")  # 64 MiB
    return conn


class FsIndexUnavailable(Exception):
    pass


class FsIndexDBHandler:
    """Read-only sessions on the fs-index SQLite file.

    Not `SyncDBHandler`: that one is Postgres-only and keeps its session registry on the class, so a second
    instance would replace the main one. The file may not exist yet when the app starts (the worker creates
    it), so the engine is created on first use.
    """

    def __init__(self, db_file: str, default_row_limit: int | None = None):
        self.db_file = db_file
        self.default_row_limit = default_row_limit
        self._engine: sa.Engine | None = None
        self._session_factory: orm.sessionmaker[SyncSession] | None = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return os.path.isfile(self.db_file)

    def _connect(self) -> orm.sessionmaker[SyncSession]:
        with self._lock:
            if self._session_factory is not None:
                return self._session_factory
            check_sqlite_version()
            # mode=ro never creates the file; a missing file fails on connect instead
            engine = sa.create_engine(
                f"sqlite:///file:{self.db_file}?mode=ro&uri=true",
                # the worker may delete and rebuild the file on a schema change
                pool_recycle=600,
            )

            @event.listens_for(engine, "connect")
            def _on_connect(dbapi_conn, _):
                cursor = dbapi_conn.cursor()
                cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
                cursor.execute("PRAGMA query_only=ON")
                cursor.close()

            self._engine = engine
            self._session_factory = orm.sessionmaker(
                bind=engine, class_=SyncSession, default_limit=self.default_row_limit, expire_on_commit=False,
            )
            return self._session_factory

    def get_session(self) -> SyncSession:
        if not self.available:
            raise FsIndexUnavailable(f"fs-index {self.db_file} does not exist")
        session = self._connect()()
        try:
            version = session.execute(sa.text("PRAGMA user_version")).scalar()
        except sa.exc.OperationalError as e:
            session.close()
            raise FsIndexUnavailable(str(e)) from e
        if version != SCHEMA_VERSION:
            session.close()
            raise FsIndexUnavailable(f"fs-index schema version {version}, expected {SCHEMA_VERSION}")
        return session

    def close(self) -> None:
        with self._lock:
            if self._engine is not None:
                self._engine.dispose()
            self._engine = None
            self._session_factory = None
