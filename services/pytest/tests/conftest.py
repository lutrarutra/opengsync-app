import pytest
import uuid
import sqlalchemy as sa

from opengsync_db import SyncDBHandler
from opengsync_db.models.Base import Base

@pytest.fixture(scope="function")  # type: ignore
def db():
    db_name = f"db{uuid.uuid4().hex}"
    engine = sa.create_engine(SyncDBHandler.AdminURL(
        user="admin", password="password", host="postgres", port=5434, db="postgres"
    ))
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(sa.text(f"CREATE DATABASE {db_name}"))
    engine.dispose()

    db = SyncDBHandler(auto_open=False, expire_on_commit=False, auto_commit=True)
    db.connect(user="admin", password="password", host="postgres", port=5434, db=db_name)
    with db._engine.begin() as conn:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        db.info("Created pg_trgm extension")
        
        Base.metadata.create_all(conn)
        db.info("Successfully created all tables")
    db.open_session()
    yield db
    db.close_session()
