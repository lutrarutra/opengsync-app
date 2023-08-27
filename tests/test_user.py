import pytest

import sqlalchemy

from limbless import models
from limbless.core import exceptions, DBHandler

@pytest.fixture(scope="function", autouse=True)
def db_handler():
    return DBHandler(":memory:", create_admin=False)

def test_create_user(db_handler):
    user = db_handler.create_user(
        email="user",
        password="1234",
        role=1
    )
    assert user.id is not None
    assert user.role is not None
    assert user.password is not None
    assert user.email == "user"

    # invalid user role
    with pytest.raises(exceptions.InvalidRole):
        db_handler.create_user(
            email="user",
            password="1234",
            role=-1
        )

    users = db_handler.get_users()
    assert len(users) == 1
    assert users[0] == user

def test_duplicate_user(db_handler):
    with pytest.raises(exceptions.NotUniqueValue):
        db_handler.create_user(
            email="user",
            password="1234",
            role=1
        )
        db_handler.create_user(
            email="user",
            password="1234",
            role=1
        )


def test_get_user(db_handler):
    user = db_handler.create_user(
        email="user",
        password="1234",
        role=1
    )

    q_user = db_handler.get_user(user.id)
    assert q_user == user

def test_update_user(db_handler):
    user = db_handler.create_user(
        email="user",
        password="1234",
        role=1
    )
    
    user.email = "user2"
    db_handler.update_user(user.id, email="user2")
    assert user.email == "user2"

    # non existent user_id
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.update_user(-1, email="user2")

    # invalid user role
    with pytest.raises(exceptions.InvalidRole):
        db_handler.update_user(user.id, role=-1)

def test_delete_user(db_handler):
    user = db_handler.create_user(
        email="user",
        password="1234",
        role=1
    )

    db_handler.delete_user(user.id)
    assert db_handler.get_user(user.id) is None

    # Non existent user_id
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.delete_user(-1)
