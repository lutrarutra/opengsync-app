import pytest
import uuid
import sqlalchemy as sa

from opengsync_db import DBHandler

@pytest.fixture(scope="function")  # type: ignore
def db():
    db_name = f"db{uuid.uuid4().hex}"
    engine = sa.create_engine(DBHandler.AdminURL(
        user="admin", password="password", host="postgres", port=5434, db="postgres"
    ))
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(sa.text(f"CREATE DATABASE {db_name}"))
    engine.dispose()

    db = DBHandler(auto_open=False, expire_on_commit=False, auto_commit=True)
    db.connect(user="admin", password="password", host="postgres", port=5434, db=db_name)
    db.create_tables()
    db.open_session()
    yield db
    db.close_session()
