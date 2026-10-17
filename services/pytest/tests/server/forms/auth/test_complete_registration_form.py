"""CompleteRegistrationForm: token checks, validation, CSRF, and user persistence."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q
from opengsync_db.categories import UserRole

from ....conftest import PASSWORD
from ..._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    OpenGSyncTestClient,
    post_form,
    post_form_csrf_mismatch,
)

CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"
TOKEN_INVALID_MSG = "Token expired or invalid."
USER_EXISTS_MSG = "User already exists."
NEW_EMAIL = "complete-reg@example.com"


def _token(
    email: str,
    role: UserRole = UserRole.CLIENT,
    valid_minutes: int = 60 * 24,
) -> str:
    from server.core import secrets

    return secrets.generate_registration_token(
        email=email, role=role, valid_minutes=valid_minutes,
    )


def _path(token: str) -> str:
    return f"/htmx/auth/complete-registration/{token}"


def _payload(email: str = NEW_EMAIL, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "email": email,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "password": PASSWORD,
        "confirm": PASSWORD,
    }
    data.update(overrides)
    return data


def _complete(client: TestClient, token: str, **overrides: object):
    from server.core import secrets

    posted_email = overrides.pop("email", None)
    if posted_email is None:
        verified = secrets.verify_registration_token(token)
        posted_email = verified[0] if verified is not None else NEW_EMAIL
    return post_form(client, _path(token), _payload(email=str(posted_email), **overrides))


def test_complete_registration_get_renders_form(client: TestClient):
    token = _token(NEW_EMAIL)
    response = get(client, _path(token))
    assert response.status_code == 200
    assert 'name="email"' in response.text
    assert NEW_EMAIL in response.text
    assert 'name="first_name"' in response.text
    assert 'name="last_name"' in response.text
    assert 'name="password"' in response.text
    assert 'name="confirm"' in response.text
    assert 'name="csrf_token"' in response.text


def test_complete_registration_get_invalid_token_shows_error(client: TestClient):
    response = get(client, _path("not-a-real-token"))
    assert response.status_code == 200
    assert TOKEN_INVALID_MSG in response.text


def test_complete_registration_valid_creates_user_and_redirects(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)

    response = _complete(client, token)

    assert_htmx_redirect(response, contains="/auth/login")
    assert_flash(response, "Registration completed successfully.", category="success")

    session.expire_all()
    created = session.first(Q.user.select(email=NEW_EMAIL))
    assert created is not None
    assert created.first_name == "Ada"
    assert created.last_name == "Lovelace"
    assert created.role == UserRole.CLIENT
    assert created.password != PASSWORD


def test_complete_registration_persists_role_from_token(
    client: TestClient, session: SyncSession,
):
    email = "complete-tech@example.com"
    token = _token(email, role=UserRole.TECHNICIAN)

    response = _complete(client, token, email=email)

    assert_htmx_redirect(response, contains="/auth/login")
    session.expire_all()
    created = session.get_one(Q.user.select(email=email))
    assert created.role == UserRole.TECHNICIAN


def test_complete_registration_can_login_afterwards(client: TestClient):
    token = _token(NEW_EMAIL)
    _complete(client, token)

    login = post_form(
        client,
        "/htmx/auth/login",
        {"email": NEW_EMAIL, "password": PASSWORD},
    )
    assert_htmx_redirect(login, contains="/")
    assert_flash(login, "Logged In!", category="success")


def test_complete_registration_expired_token_rerenders(
    client: TestClient, session: SyncSession,
):
    # Far enough in the past that timezone skew cannot keep the JWT valid.
    # generate_registration_token uses naive datetime.now() for `exp`, which
    # PyJWT treats as UTC — see the report on that mismatch.
    token = _token(NEW_EMAIL, valid_minutes=-60 * 24)

    get_response = get(client, _path(token))
    assert get_response.status_code == 200
    assert TOKEN_INVALID_MSG in get_response.text

    response = _complete(client, token)
    assert_form_invalid(response, contains=TOKEN_INVALID_MSG)
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_unknown_token_rerenders(
    client: TestClient, session: SyncSession,
):
    response = _complete(client, "not-a-real-token")
    assert_form_invalid(response, contains=TOKEN_INVALID_MSG)
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_password_reset_token_rejected(
    client: TestClient, session: SyncSession, user,
):
    from server.core import secrets

    token = secrets.create_password_reset_token(user.id)
    response = _complete(client, token)
    assert_form_invalid(response, contains=TOKEN_INVALID_MSG)
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_already_used_token_rerenders(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    first = _complete(client, token)
    assert_htmx_redirect(first, contains="/auth/login")

    response = _complete(client, token)
    assert_form_invalid(response, contains=USER_EXISTS_MSG)
    assert session.count(Q.user.select(email=NEW_EMAIL)) == 1


def test_complete_registration_existing_user_rerenders(
    client: TestClient, session: SyncSession, user,
):
    token = _token(user.email)
    before = session.count(Q.user.select())

    response = _complete(client, token, email=user.email)

    assert_form_invalid(response, contains=USER_EXISTS_MSG)
    assert session.count(Q.user.select()) == before


def test_register_existing_user_does_not_issue_completion_link(
    client: OpenGSyncTestClient, fake_mailer, session: SyncSession, user,
):
    response = post_form(client, "/htmx/auth/register", {"email": user.email})

    assert_htmx_redirect(response, contains="/auth/login")
    assert fake_mailer.welcome_back == [user.email]
    assert fake_mailer.registration == []
    before = session.count(Q.user.select())

    assert session.count(Q.user.select()) == before


def test_complete_registration_posted_email_must_match_token(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    response = _complete(
        client, token, email="other@example.com",
    )
    assert_form_invalid(response, contains=TOKEN_INVALID_MSG)
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None
    assert session.first(Q.user.select(email="other@example.com")) is None


def test_complete_registration_short_password_rerenders(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    response = _complete(
        client, token, password="short", confirm="short",
    )
    assert_form_invalid(response)
    assert "at least 8" in response.text
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_missing_fields_rerenders(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    response = post_form(
        client,
        _path(token),
        {
            "email": NEW_EMAIL,
            "first_name": "",
            "last_name": "",
            "password": "",
            "confirm": "",
        },
    )
    assert_form_invalid(response)
    assert "First Name is required" in response.text
    assert "Last Name is required" in response.text
    assert "Password is required" in response.text
    assert "Confirm Password is required" in response.text
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_first_name_too_long_rerenders(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    response = _complete(client, token, first_name="A" * 65)
    assert_form_invalid(response)
    assert "64" in response.text
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_password_mismatch_rerenders(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    response = _complete(
        client, token, password=PASSWORD, confirm="different-password",
    )
    assert_form_invalid(response, contains="match")
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_csrf_mismatch_rerenders(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    response = post_form_csrf_mismatch(client, _path(token), _payload())
    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None
