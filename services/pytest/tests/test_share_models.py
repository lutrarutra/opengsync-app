from opengsync_db import DBHandler, models

from .create_units import create_user


def test_share_models(db: DBHandler):
    user = create_user(db)

    token = models.ShareToken(
        time_valid_min=10,
        owner_id=user.id,
    )

    db.session.add(token)
    db.session.flush()

    assert token.uuid is not None