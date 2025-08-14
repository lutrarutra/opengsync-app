from datetime import datetime
from typing import Optional, Union

import loguru

import sqlalchemy as sa
from sqlalchemy import orm

from ..models.Base import Base
from .. import models


class DBHandler():
    Session: orm.scoped_session

    def __init__(self, logger: Optional["loguru.Logger"] = None, expire_on_commit: bool = False, auto_open: bool = True) -> None:
        self._logger = logger
        self._session: orm.Session | None = None
        self._connection: sa.engine.Connection | None = None
        self.expire_on_commit = expire_on_commit
        self.__needs_commit = False
        self.auto_open = auto_open

        from .model_handlers._seq_request_methods import SeqRequestBP
        from .model_handlers._library_methods import LibraryBP
        from .model_handlers._project_methods import ProjectBP
        from .model_handlers._experiment_methods import ExperimentBP
        from .model_handlers._sample_methods import SampleBP
        from .model_handlers._pool_methods import PoolBP
        from .model_handlers._user_methods import UserBP
        from .model_handlers._index_kit_methods import IndexKitBP
        from .model_handlers._contact_methods import ContactBP
        from .model_handlers._lane_methods import LaneBP
        from .model_handlers._feature_methods import FeatureBP
        from .model_handlers._feature_kit_methods import FeatureKitBP
        from .model_handlers._sequencer_methods import SequencerBP
        from .model_handlers._adapter_methods import AdapterBP
        from .model_handlers._plate_methods import PlateBP
        from .model_handlers._barcode_methods import BarcodeBP
        from .model_handlers._lab_prep_methods import LabPrepBP
        from .model_handlers._kit_methods import KitBP
        from .model_handlers._link_methods import LinkBP
        from .model_handlers._file_methods import FileBP
        from .model_handlers._comment_methods import CommentBP
        from .model_handlers._seq_run_methods import SeqRunBP
        from .model_handlers._event_methods import EventBP
        from .model_handlers._group_methods import GroupBP
        from .model_handlers._share_methods import ShareBP
        from .pd_handler import PDBlueprint

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
        self.files = FileBP("files", self)
        self.comments = CommentBP("comments", self)
        self.seq_runs = SeqRunBP("seq_runs", self)
        self.events = EventBP("events", self)
        self.groups = GroupBP("groups", self)
        self.shares = ShareBP("shares", self)
        self.pd = PDBlueprint("pd", self)

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

    def close_session(self, commit: bool = True, rollback: bool = False) -> None:
        if self._session is None:
            self.warn("Session is already closed or was never opened.")
            return
       
        if commit and not rollback:
            if self.__needs_commit or self.session.dirty or self.session.new or self.session.deleted:
                try:
                    self.session.commit()
                except Exception:
                    self.error("Commit failed: - rolling back transaction.")
                    self.session.rollback()
                    raise
        elif rollback:
            self.info("Rolling back transaction...")
            self.session.rollback()
        else:
            if not commit and self.__needs_commit:
                self.warn("Session was not committed, but changes were made. This may lead to data loss.")

        self._session = DBHandler.Session.remove()

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