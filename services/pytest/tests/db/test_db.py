from opengsync_db import SyncDBHandler, queries as Q

from .create_units import create_user


def test_db(db: SyncDBHandler):
    user_1 = create_user(db)
    assert user_1 is not None

    user_2 = create_user(db)
    assert user_2 is not None

    assert len(db.session.get_all(Q.user.select(), limit=None)) == db.session.count(Q.user.select()) == 2

    db.close_session(rollback=True)
    db.open_session()

    assert len(db.session.get_all(Q.user.select(), limit=None)) == db.session.count(Q.user.select()) == 0

    create_user(db)

    assert len(db.session.get_all(Q.user.select(), limit=None)) == db.session.count(Q.user.select()) == 1

    db.session.commit()

    create_user(db)

    assert len(db.session.get_all(Q.user.select(), limit=None)) == db.session.count(Q.user.select()) == 2

    db.session.rollback()

    assert len(db.session.get_all(Q.user.select(), limit=None)) == db.session.count(Q.user.select()) == 1