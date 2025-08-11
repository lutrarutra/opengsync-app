import os
import pytest

from opengsync_db import DBHandler
from opengsync_db.models.Base import Base

db_user = os.environ["POSTGRES_USER"]
db_password = os.environ["POSTGRES_PASSWORD"]
db_host = os.environ["POSTGRES_HOST"]
db_port = os.environ["POSTGRES_PORT"]
db_name = os.environ["POSTGRES_DB"]


@pytest.fixture(scope="session")  # type: ignore
def _db():
    db = DBHandler()
    db.connect(user=db_user, password=db_password, host=db_host, port=db_port, db=db_name)
    Base.metadata.drop_all(db._engine)
    db.create_tables()
    yield db
    db._engine.dispose()


@pytest.fixture(scope="function")  # type: ignore
def db(_db: DBHandler):
    _db.open_session()
    yield _db
    _db.close_session(rollback=True)
