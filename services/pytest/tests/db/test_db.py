from opengsync_db import SyncSession, queries as Q

from .create_units import create_user


def test_db(session: SyncSession):
    user_1 = create_user(session)
    assert user_1 is not None

    user_2 = create_user(session)
    assert user_2 is not None

    assert len(session.get_all(Q.user.select(), limit=None)) == session.count(Q.user.select()) == 2

    session.rollback()

    assert len(session.get_all(Q.user.select(), limit=None)) == session.count(Q.user.select()) == 0

    create_user(session)

    assert len(session.get_all(Q.user.select(), limit=None)) == session.count(Q.user.select()) == 1

    session.commit()

    create_user(session)

    assert len(session.get_all(Q.user.select(), limit=None)) == session.count(Q.user.select()) == 2

    session.rollback()

    assert len(session.get_all(Q.user.select(), limit=None)) == session.count(Q.user.select()) == 1