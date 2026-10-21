"""ActivationForm: link of the reactivation email — single-use token, password, and the organization/PI a customer
must fill in if missing."""

import datetime as dt
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ..._http import assert_form_invalid, assert_htmx_redirect, get, post_form
from ..._profile import new_profile_payload, set_profile, INSTITUTE, DEPARTMENT, PI_NAME, PI_EMAIL

NEW_PASSWORD = "new-password1"
INVALID_MSG = "Link expired or invalid."


def _token(user_id: int, valid_minutes: int = 60 * 24) -> str:
    from server.core import secrets
    return secrets.create_activation_token(user_id=user_id, valid_minutes=valid_minutes)


def _path(token: str) -> str:
    return f"/htmx/auth/activate/{token}"


def _payload(email: str, **overrides: str) -> dict[str, str]:
    return {"email": email, "password": NEW_PASSWORD, "confirm": NEW_PASSWORD, **new_profile_payload(), **overrides}


def _reload(session: SyncSession, user: models.User) -> models.User:
    session.expire_all()
    return session.get_one(Q.user.select(id=user.id))


def _password_ok(user: models.User, password: str) -> bool:
    from server.core import secrets
    return secrets.BcryptCompat().check_password_hash(user.password, password)


def test_activate_user_sends_activation_link(
    client: TestClient, session: SyncSession, user, insider_token: str, fake_mailer,
):
    user.role = C.UserRole.DEACTIVATED
    session.commit()

    post_form(client, f"/htmx/auth/{user.id}/activate", {}, token=insider_token)

    assert fake_mailer.password_reset == []
    [(recipient, link)] = fake_mailer.activation
    assert recipient == user.email
    token = urlparse(link).path.rsplit("/", 1)[-1]
    assert get(client, _path(token)).status_code == 200


def test_render_asks_profile_of_customer_missing_it(client: TestClient, user):
    response = get(client, _path(_token(user.id)))

    assert response.status_code == 200
    assert user.email in response.text
    assert 'name="institute"' in response.text and 'name="pi"' in response.text


def test_render_skips_complete_profile_and_insiders(client: TestClient, session: SyncSession, user, insider):
    set_profile(session, user)
    session.commit()

    for account in (user, insider):
        response = get(client, _path(_token(account.id)))
        assert response.status_code == 200
        assert 'name="institute"' not in response.text


def test_activation_sets_password_and_profile(client: TestClient, session: SyncSession, user):
    response = post_form(client, _path(_token(user.id)), _payload(user.email))

    assert_htmx_redirect(response, contains="/auth/login")
    reloaded = _reload(session, user)
    assert _password_ok(reloaded, NEW_PASSWORD)
    assert (reloaded.institute, reloaded.department, reloaded.pi_name, reloaded.pi_email) == (
        INSTITUTE, DEPARTMENT, PI_NAME, PI_EMAIL,
    )


def test_activation_requires_missing_profile(client: TestClient, session: SyncSession, user):
    set_profile(session, user, pi_name=None, pi_email=None)
    session.commit()
    password = user.password

    response = post_form(
        client, _path(_token(user.id)), _payload(user.email, **{"pi": "", "pi-text": "", "pi_email": ""}),
    )

    assert_form_invalid(response, contains="Principal Investigator is required.")
    assert _reload(session, user).password == password


def test_activation_keeps_complete_profile(client: TestClient, session: SyncSession, user):
    set_profile(session, user)
    session.commit()

    response = post_form(client, _path(_token(user.id)), {"email": user.email, "password": NEW_PASSWORD, "confirm": NEW_PASSWORD})

    assert_htmx_redirect(response, contains="/auth/login")
    assert _reload(session, user).institute == INSTITUTE


def test_activation_link_is_single_use(client: TestClient, session: SyncSession, user):
    token = _token(user.id)
    assert_htmx_redirect(post_form(client, _path(token), _payload(user.email)), contains="/auth/login")

    assert INVALID_MSG in get(client, _path(token)).text
    response = post_form(client, _path(token), _payload(user.email, password="other-password1", confirm="other-password1"))
    assert_form_invalid(response, contains=INVALID_MSG)
    assert _password_ok(_reload(session, user), NEW_PASSWORD)


def test_activation_rejects_other_tokens(client: TestClient, user):
    from server.core import secrets

    for token in ("garbage", secrets.create_password_reset_token(user_id=user.id), _token(user.id, valid_minutes=-1)):
        assert INVALID_MSG in get(client, _path(token)).text


def test_activation_rejects_deactivated_user(client: TestClient, session: SyncSession, user):
    user.role = C.UserRole.DEACTIVATED
    session.commit()

    assert INVALID_MSG in get(client, _path(_token(user.id))).text


def test_activation_password_mismatch(client: TestClient, session: SyncSession, user):
    password = user.password
    response = post_form(client, _path(_token(user.id)), _payload(user.email, confirm="different-password1"))

    assert_form_invalid(response, contains="Passwords must match.")
    assert _reload(session, user).password == password
