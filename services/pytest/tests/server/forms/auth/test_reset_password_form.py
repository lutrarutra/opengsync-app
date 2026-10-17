"""ResetPasswordForm: token validation, password validation, persistence, and CSRF."""

from urllib.parse import urlparse

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q

from ....conftest import PASSWORD
from ..._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

PATH = "/htmx/auth/reset-password"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"
TOKEN_INVALID_MSG = "Token expired or invalid."
MISMATCH_MSG = "Passwords must match."
NEW_PASSWORD = "new-password1"


def _token(user_id: int, valid_minutes: int = 60 * 24) -> str:
    from server.core import secrets

    return secrets.create_password_reset_token(
        user_id=user_id,
        valid_minutes=valid_minutes,
    )


def _path(token: str) -> str:
    return f"{PATH}/{token}"


def _payload(
    email: str,
    password: str = NEW_PASSWORD,
    confirm: str = NEW_PASSWORD,
) -> dict[str, str]:
    return {
        "email": email,
        "password": password,
        "confirm": confirm,
    }


def _reset(
    client: TestClient,
    token: str,
    email: str,
    *,
    password: str = NEW_PASSWORD,
    confirm: str = NEW_PASSWORD,
):
    return post_form(
        client,
        _path(token),
        _payload(email, password=password, confirm=confirm),
    )


def test_reset_password_get_renders_form(client: TestClient, user):
    response = get(client, _path(_token(user.id)))

    assert response.status_code == 200
    assert 'name="email"' in response.text
    assert user.email in response.text
    assert 'name="password"' in response.text
    assert 'name="confirm"' in response.text
    assert 'name="csrf_token"' in response.text


def test_reset_password_expired_token_get_rerenders(client: TestClient, user):
    response = get(client, _path(_token(user.id, valid_minutes=-60 * 24)))

    assert response.status_code == 200
    assert TOKEN_INVALID_MSG in response.text


def test_reset_password_unknown_token_get_rerenders(client: TestClient):
    response = get(client, _path("not-a-real-token"))

    assert response.status_code == 200
    assert TOKEN_INVALID_MSG in response.text


def test_reset_password_valid_token_persists_password_and_redirects(
    client: TestClient,
    session: SyncSession,
    user,
):
    response = _reset(client, _token(user.id), user.email)

    assert_htmx_redirect(response, contains="/auth/login")
    assert_flash(response, "Password updated!", category="success")

    session.expire_all()
    changed = session.get_one(Q.user.select(id=user.id))
    from server.core.secrets import BcryptCompat

    assert changed.pw_set_datetime is not None
    assert BcryptCompat().check_password_hash(changed.password, NEW_PASSWORD)
    assert not BcryptCompat().check_password_hash(changed.password, PASSWORD)


def test_reset_password_expired_token_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
):
    response = _reset(
        client,
        _token(user.id, valid_minutes=-60 * 24),
        user.email,
    )

    assert_form_invalid(response, contains=TOKEN_INVALID_MSG)
    session.expire_all()
    persisted = session.get_one(Q.user.select(id=user.id))
    from server.core.secrets import BcryptCompat

    assert BcryptCompat().check_password_hash(persisted.password, PASSWORD)


def test_reset_password_unknown_token_rerenders(client: TestClient, user):
    response = _reset(client, "not-a-real-token", user.email)

    assert_form_invalid(response, contains=TOKEN_INVALID_MSG)


def test_reset_password_missing_user_token_rerenders(client: TestClient):
    response = get(client, _path(_token(999999)))

    assert response.status_code == 404


def test_reset_password_already_used_token_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
):
    token = _token(user.id)
    first = _reset(client, token, user.email)
    assert_htmx_redirect(first, contains="/auth/login")

    response = _reset(
        client,
        token,
        user.email,
        password="another-password1",
        confirm="another-password1",
    )

    assert_form_invalid(response, contains=TOKEN_INVALID_MSG)
    session.expire_all()
    persisted = session.get_one(Q.user.select(id=user.id))
    from server.core.secrets import BcryptCompat

    assert BcryptCompat().check_password_hash(persisted.password, NEW_PASSWORD)


def test_reset_password_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
):
    response = _reset(
        client,
        _token(user.id),
        user.email,
        confirm="different-password",
    )

    assert_form_invalid(response, contains=MISMATCH_MSG)
    session.expire_all()
    persisted = session.get_one(Q.user.select(id=user.id))
    from server.core.secrets import BcryptCompat

    assert BcryptCompat().check_password_hash(persisted.password, PASSWORD)


def test_reset_password_short_password_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
):
    response = _reset(
        client,
        _token(user.id),
        user.email,
        password="short",
        confirm="short",
    )

    assert_form_invalid(response)
    assert "at least 8" in response.text
    session.expire_all()
    persisted = session.get_one(Q.user.select(id=user.id))
    from server.core.secrets import BcryptCompat

    assert BcryptCompat().check_password_hash(persisted.password, PASSWORD)


def test_reset_password_missing_fields_rerenders(client: TestClient, user):
    response = post_form(
        client,
        _path(_token(user.id)),
        {
            "email": user.email,
            "password": "",
            "confirm": "",
        },
    )

    assert_form_invalid(response)
    assert "Password is required" in response.text
    assert "Confirm Password is required" in response.text


def test_reset_password_csrf_mismatch_rerenders(client: TestClient, user):
    response = post_form_csrf_mismatch(
        client,
        _path(_token(user.id)),
        _payload(user.email),
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")


def test_reset_password_request_sends_link(
    client: TestClient,
    fake_mailer,
    user,
    user_token: str,
):
    response = post_form(
        client,
        f"/htmx/auth/{user.id}/reset-password",
        {},
        token=user_token,
    )

    assert_htmx_redirect(response, contains="/auth/login")
    assert_flash(response, "Password reset email sent!", category="success")
    assert fake_mailer.password_reset

    recipient, link = fake_mailer.password_reset[0]
    assert recipient == user.email
    parsed = urlparse(link)
    prefix = "/auth/reset-password/"
    assert parsed.path.startswith(prefix)
    assert not parsed.query
    reset_token = parsed.path.removeprefix(prefix)

    from server.core import secrets

    assert secrets.verify_password_reset_token(reset_token) == user.id
