import threading
from typing import Optional, Union

import loguru
from sqlalchemy import create_engine, Engine
from sqlalchemy import orm
import sqlalchemy as sa

from .SyncSession import SyncSession

class SyncDBHandler:
    Session: orm.scoped_session
    session_factory: orm.sessionmaker[SyncSession]
    
    def __init__(
        self,
        logger: Optional["loguru.Logger"] = None,
        expire_on_commit: bool = False,
        auto_commit: bool = False,
    ):
        self._logger = logger
        self._engine: Optional[Engine] = None
        self.expire_on_commit = expire_on_commit
        self.auto_commit = auto_commit
        self._local = threading.local()

    def connect(
        self, user: str, password: str, host: str, db: str = "token_db", port: Union[str, int] = 5432
    ) -> None:
        self._url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
        self.public_url = f"postgresql+psycopg://{host}:{port}/{db}"
        
        self._engine = create_engine(
            self._url, pool_pre_ping=True,
        )

        try:
            with self._engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
        except Exception as e:
            raise Exception(f"Could not connect to DB '{self.public_url}':\n{e}")
            
        self.session_factory = orm.sessionmaker(
            bind=self._engine, 
            expire_on_commit=self.expire_on_commit,
            class_=SyncSession,
        )
        SyncDBHandler.Session = orm.scoped_session(self.session_factory)

    @property
    def _session(self) -> SyncSession | None:
        """Thread-local session storage"""
        return getattr(self._local, 'session', None)
    
    @_session.setter
    def _session(self, value: SyncSession | None):
        self._local.session = value


    @property
    def session(self) -> SyncSession:
        if self._session is None:
            raise Exception("Session is not open.")
        return self._session

    def open_session(self, autoflush: bool = True) -> SyncSession:
        if self._session is not None:
            self.warn("Session is already open")
            return self._session
        self._session = SyncDBHandler.Session(autoflush=autoflush)
        return self._session
    
    def close_session(self, commit: bool | None = None, rollback: bool = False) -> bool:
        """ returns True if db was modified """
        modified = False
        if self._session is None:
            self.warn("Session is already closed or was never opened.")
            return False
        
        if commit is None:
            commit = self.auto_commit
            
        try:
            if commit and not rollback:
                try:
                    self._session.commit()
                    modified = True
                except Exception:
                    self.error("Commit failed: - rolling back transaction.")
                    self._session.rollback()
                    raise
            elif rollback:
                self.info("Rolling back transaction...")
                self._session.rollback()
        finally:
            SyncDBHandler.Session.remove()
            self._session = None
            
        return modified

    def close(self) -> None:
        """Dispose the engine pool."""
        if self._engine:
            self._engine.dispose()

    def info(self, *values: object) -> None:
        message = " ".join([str(value) for value in values])
        if self._logger is not None:
            self._logger.opt(depth=1).info(message)
        else:
            print(f"LOG: {message}")
    
    def error(self, *values: object) -> None:
        message = " ".join([str(value) for value in values])
        if self._logger is not None:
            self._logger.opt(depth=1).error(message)
        else:
            print(f"ERROR: {message}")
            
    def warn(self, *values: object) -> None:
        message = " ".join([str(value) for value in values])
        if self._logger is not None:
            self._logger.opt(depth=1).warning(message)
        else:
            print(f"WARNING: {message}")
            
    def debug(self, *values: object) -> None:
        message = " ".join([str(value) for value in values])
        if self._logger is not None:
            self._logger.opt(depth=1).debug(message)
        else:
            print(f"DEBUG: {message}")