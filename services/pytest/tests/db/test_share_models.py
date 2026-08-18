from opengsync_db import SyncSession, models

from .create_units import create_user


def test_share_models(session: SyncSession):
    user = create_user(session)

    token = models.ShareToken(
        time_valid_min=10,
        owner_id=user.id,
    )

    session.add(token)
    session.flush()

    assert token.uuid is not None