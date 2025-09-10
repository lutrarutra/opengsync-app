from datetime import datetime
from typing import Optional, Union

import loguru

import sqlalchemy as sa
from sqlalchemy import orm

from ..models.Base import Base
from .. import models


class DBHandler():
    Session: orm.scoped_session
    lab_protocol_start_number: int

    def __init__(
        self, logger: Optional["loguru.Logger"] = None,
        expire_on_commit: bool = False, auto_open: bool = False,
        lab_protocol_start_number: int = 1
    ):
        self._logger = logger
        self._session: orm.Session | None = None
        self._connection: sa.engine.Connection | None = None
        self.expire_on_commit = expire_on_commit
        self.lab_protocol_start_number = lab_protocol_start_number
        self.__needs_commit = False
        self.auto_open = auto_open

        from .blueprints.SeqRequestBP import SeqRequestBP
        from .blueprints.LibraryBP import LibraryBP
        from .blueprints.ProjectBP import ProjectBP
        from .blueprints.ExperimentBP import ExperimentBP
        from .blueprints.SampleBP import SampleBP
        from .blueprints.PoolBP import PoolBP
        from .blueprints.UserBP import UserBP
        from .blueprints.IndexKitBP import IndexKitBP
        from .blueprints.ContactBP import ContactBP
        from .blueprints.LaneBP import LaneBP
        from .blueprints.FeatureBP import FeatureBP
        from .blueprints.FeatureKitBP import FeatureKitBP
        from .blueprints.SequencerBP import SequencerBP
        from .blueprints.AdapterBP import AdapterBP
        from .blueprints.PlateBP import PlateBP
        from .blueprints.BarcodeBP import BarcodeBP
        from .blueprints.LabPrepBP import LabPrepBP
        from .blueprints.KitBP import KitBP
        from .blueprints.LinkBP import LinkBP
        from .blueprints.MediaFileBP import MediaFileBP
        from .blueprints.CommentBP import CommentBP
        from .blueprints.SeqRunBP import SeqRunBP
        from .blueprints.EventBP import EventBP
        from .blueprints.GroupBP import GroupBP
        from .blueprints.ShareBP import ShareBP
        from .blueprints.DataPathBP import DataPathBP
        from .blueprints.PandasBP import PandasBP

        self.seq_requests = SeqRequestBP("seq_requests", self)
        self.libraries = LibraryBP("libraries", self)
        self.projects = ProjectBP("projects", self)
        self.experiments = ExperimentBP("experiments", self)
        self.samples = SampleBP("samples", self)
        self.pools = PoolBP("pools", self)
        self.users = UserBP("users", self)
        self.index_kits = IndexKitBP("index_kits", self)
        self.contacts = ContactBP("contacts", self)
        self.lanes = LaneBP("lanes", self)
        self.features = FeatureBP("features", self)
        self.feature_kits = FeatureKitBP("feature_kits", self)
        self.sequencers = SequencerBP("sequencers", self)
        self.adapters = AdapterBP("adapters", self)
        self.plates = PlateBP("plates", self)
        self.barcodes = BarcodeBP("barcodes", self)
        self.lab_preps = LabPrepBP("lab_preps", self)
        self.kits = KitBP("kits", self)
        self.links = LinkBP("links", self)
        self.media_files = MediaFileBP("media_files", self)
        self.comments = CommentBP("comments", self)
        self.seq_runs = SeqRunBP("seq_runs", self)
        self.events = EventBP("events", self)
        self.groups = GroupBP("groups", self)
        self.shares = ShareBP("shares", self)
        self.data_paths = DataPathBP("data_paths", self)
        self.pd = PandasBP("pd", self)

    def connect(
        self, user: str, password: str, host: str, db: str = "opengsync_db", port: Union[str, int] = 5432
    ) -> None:
        self._url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
        self.public_url = f"{self._url.split(':')[0]}://{host}:{port}/{db}"
        self._engine = sa.create_engine(self._url)
        try:
            self._connection = self._engine.connect()
        except Exception as e:
            raise Exception(f"Could not connect to DB '{self.public_url}':\n{e}")
        
        self.info(f"Connected to DB '{self.public_url}'")

        self.session_factory = orm.sessionmaker(bind=self._engine, expire_on_commit=self.expire_on_commit)
        DBHandler.Session = orm.scoped_session(self.session_factory)
        from . import listeners  # noqa: F401

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

    @property
    def session(self) -> orm.Session:
        if self._session is None:
            raise Exception("Session is not open.")
        return self._session

    @property
    def connection(self) -> sa.engine.Connection:
        if self._connection is None:
            raise Exception("Connection is not open.")
        return self._connection

    def timestamp(self) -> datetime:
        return datetime.now()
    
    def commit(self) -> None:
        if self._session is not None:
            self._session.commit()
        else:
            raise Exception("Session is not open, cannot commit changes.")

    def flush(self) -> None:
        if self._session is not None:
            self.__needs_commit = True
            self._session.flush()
        else:
            raise Exception("Session is not open, cannot flush changes.")

    def refresh(self, obj: object) -> None:
        if self._session is not None:
            self._session.refresh(obj)
        else:
            raise Exception("Session is not open, cannot refresh session state.")
        
    def create_tables(self) -> None:
        """Create database tables with pg_trgm extension if needed."""
        inspector = sa.inspect(self._engine)
        
        if inspector.has_table(models.User.__tablename__):
            self.warn("Tables already exist, skipping creation...")
            return
        
        try:
            with self._engine.begin() as conn:
                conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                self.info("Created pg_trgm extension")
                
                Base.metadata.create_all(conn)
                self.info("Successfully created all tables")
                
        except Exception as e:
            self.error(f"Failed to create tables: {str(e)}")
            raise RuntimeError("Database initialization failed") from e

    def open_session(self, autoflush: bool = False) -> None:
        if self._session is not None:
            self.warn("Session is already open")
            return
        self._session = DBHandler.Session(autoflush=autoflush)

    def close_session(self, commit: bool = True, rollback: bool = False) -> bool:
        """ returns True if db was modified """
        modified = False
        if self._session is None:
            self.warn("Session is already closed or was never opened.")
            return False

        if commit and not rollback:
            if self.needs_commit:
                try:
                    self._session.commit()
                except Exception:
                    self.error("Commit failed: - rolling back transaction.")
                    self._session.rollback()
                    raise
                self.__needs_commit = False
                modified = True
        elif rollback:
            self.info("Rolling back transaction...")
            self._session.rollback()
        else:
            if not commit and self.__needs_commit:
                self.warn("Session was not committed, but changes were made. This may lead to data loss.")
        self._session = DBHandler.Session.remove()
        return modified

    def rollback(self) -> None:
        if self._session is None:
            self.error("Session is not open, cannot rollback.")
            raise Exception("Session is not open, cannot rollback.")
        self.info("Rolling back transaction...")
        self._session.rollback()

    def close_connection(self) -> None:
        if self._connection is not None:
            self._connection = self._connection.close()
            self.info("Connection closed.")

    def __del__(self):
        if self._session is not None:
            self.close_session()
        self.close_connection()
        self._engine.dispose()

    @property
    def needs_commit(self) -> bool:
        if self._session is None:
            return False
        return self.__needs_commit or bool(self._session.dirty) or bool(self._session.new) or bool(self._session.deleted)