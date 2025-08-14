from opengsync_db import DBHandler

from .create_units import create_user


def test_db(db: DBHandler):
    user_1 = create_user(db)
    assert user_1 is not None

    user_2 = create_user(db)
    assert user_2 is not None

    assert len(db.users.find(limit=None)[0]) == 2

    db.close_session(rollback=True)
    db.open_session()

    assert len(db.users.find(limit=None)[0]) == 0

    create_user(db)

    assert len(db.users.find(limit=None)[0]) == 1

    db.commit()

    create_user(db)

    assert len(db.users.find(limit=None)[0]) == 2

    db.rollback()

    assert len(db.users.find(limit=None)[0]) == 1