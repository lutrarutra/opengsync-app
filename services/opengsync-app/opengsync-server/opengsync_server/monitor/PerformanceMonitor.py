import sqlalchemy as sa
from sqlalchemy import orm

from .. import logger
from .RequestStat import RequestStat, MonitorBase

class PerformanceMonitor:
    Session: orm.scoped_session


    def __init__(self, user: str, password: str, host: str, db: str = "monitor", port: int | str = 5432):
        self._url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
        self.public_url = f"{self._url.split(':')[0]}://{host}:{port}/{db}"
        self._engine = sa.create_engine(self._url)
        try:
            self._connection = self._engine.connect()
        except Exception as e:
            raise Exception(f"Could not connect to DB '{self.public_url}':\n{e}")
        
        logger.info(f"Connected to DB '{self.public_url}'")

        self.session_factory = orm.sessionmaker(bind=self._engine, expire_on_commit=True)
        PerformanceMonitor.Session = orm.scoped_session(self.session_factory)
        self.create_tables()
        self._session = None

    def create_tables(self) -> None:
        """Create database tables with pg_trgm extension if needed."""
        inspector = sa.inspect(self._engine)
        
        if inspector.has_table(RequestStat.__tablename__):
            logger.warning("Tables already exist, skipping creation...")
            return
        
        try:
            with self._engine.begin() as conn:
                conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                logger.info("Created pg_trgm extension")
                
                MonitorBase.metadata.create_all(conn)
                logger.info("Successfully created all tables")
                
        except Exception as e:
            logger.error(f"Failed to create tables: {str(e)}")
            raise RuntimeError("Database initialization failed") from e
        
    @property
    def session(self) -> orm.Session:
        if self._session is None:
            raise Exception("Session is not open.")
        return self._session
        
    def open_session(self, autoflush: bool = False) -> None:
        if self._session is not None:
            logger.warning("Session is already open")
            return
        self._session = PerformanceMonitor.Session(autoflush=autoflush)

    def close_session(self, commit: bool | None = None, rollback: bool = False) -> bool:
        """ returns True if db was modified """
        modified = False
        if self._session is None:
            logger.warning("Session is already closed or was never opened.")
            return False

        if commit and not rollback:
            self._session.commit()
        elif rollback:
            logger.info("Rolling back transaction...")
            self._session.rollback()

        self._session = PerformanceMonitor.Session.remove()
        return modified