import os
import pytest

from limbless_db import DBHandler
from limbless_db.categories import UserRole


@pytest.fixture()
def db() -> DBHandler:
    db_user = os.environ["POSTGRES_USER"]
    db_password = os.environ["POSTGRES_PASSWORD"]
    db_host = os.environ["POSTGRES_HOST"]
    db_port = os.environ["POSTGRES_PORT"]
    db_name = os.environ["POSTGRES_DB"]
    db = DBHandler(user=db_user, password=db_password, host=db_host, port=db_port, db=db_name)
    db.create_tables()
    return db


def test_create_user(db: DBHandler):
    old_users, _ = db.get_users(limit=None)
    new_user = db.create_user(
        email="new@user.com",
        hashed_password="password",
        first_name="test",
        last_name="user",
        role=UserRole.ADMIN,
    )
    assert new_user.email == "new@user.com"
    assert new_user.first_name == "test"
    assert new_user.last_name == "user"
    assert new_user.role == UserRole.ADMIN
    assert new_user.password == "password"

    user = db.get_user(new_user.id)
    assert user == new_user

    users, _ = db.get_users(limit=None)
    assert len(users) == len(old_users) + 1


def test_delete_user(db: DBHandler):
    old_users, _ = db.get_users(limit=None)
    user = db.create_user(email="user", hashed_password="password", first_name="test", last_name="user", role=UserRole.ADMIN)
    assert len(old_users) + 1 == len(db.get_users(limit=None))
    db.delete_user(user.id)
    assert len(old_users) == len(db.get_users(limit=None))
