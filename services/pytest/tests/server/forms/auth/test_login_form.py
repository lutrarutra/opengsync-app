"""LoginForm: GET rendering, credential checks, CSRF, and HTMX redirects."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q
from opengsync_db.categories import UserRole

from ....conftest import PASSWORD
from ..._http import (
    assert_cookie_set,
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

LOGIN_PATH = "/htmx/auth/login"
DEACTIVATED_MSG = "Account is deactivated. Please contact us to activate your account."
INVALID_CREDS_MSG = "Invalid email or password."
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def test_login_get_renders_form(client: TestClient):
    response = get(client, LOGIN_PATH)
    assert response.status_code == 200
    assert 'name="email"' in response.text
    assert 'name="password"' in response.text
    assert 'name="csrf_token"' in response.text


def test_login_get_already_authenticated_redirects(client: TestClient, user_token: str):
    response = get(client, LOGIN_PATH, token=user_token)
    assert_htmx_redirect(response, contains="/")


def test_login_valid_sets_token_and_redirects(client: TestClient, user):
    response = post_form(
        client,
        LOGIN_PATH,
        {"email": user.email, "password": PASSWORD},
    )
    assert_htmx_redirect(response, contains="/")
    assert_cookie_set(response, "access_token")
    assert_flash(response, "Logged In!", category="success")


def test_login_valid_htmx_matches_non_htmx(client: TestClient, user):
    browser = post_form(
        client,
        LOGIN_PATH,
        {"email": user.email, "password": PASSWORD},
    )
    htmx = post_form(
        client,
        LOGIN_PATH,
        {"email": user.email, "password": PASSWORD},
        htmx=True,
    )
    assert_htmx_redirect(browser, contains="/")
    assert_htmx_redirect(htmx, contains="/")
    assert browser.headers.get("HX-Redirect") == htmx.headers.get("HX-Redirect")


def test_login_unknown_email_rerenders(client: TestClient):
    response = post_form(
        client,
        LOGIN_PATH,
        {"email": "missing@example.com", "password": PASSWORD},
    )
    assert_form_invalid(response, contains=INVALID_CREDS_MSG)
    assert "access_token" not in response.cookies


def test_login_wrong_password_rerenders(client: TestClient, user):
    response = post_form(
        client,
        LOGIN_PATH,
        {"email": user.email, "password": "wrong-password"},
    )
    assert_form_invalid(response, contains=INVALID_CREDS_MSG)
    assert "access_token" not in response.cookies


def test_login_malformed_email_treated_as_unknown(client: TestClient):
    response = post_form(
        client,
        LOGIN_PATH,
        {"email": "not-an-email", "password": PASSWORD},
    )
    assert_form_invalid(response, contains=INVALID_CREDS_MSG)


def test_login_missing_fields_rerenders(client: TestClient):
    response = post_form(client, LOGIN_PATH, {"email": "", "password": ""})
    assert_form_invalid(response)
    assert "Email is required" in response.text
    assert "Password is required" in response.text


def test_login_csrf_mismatch_rerenders(client: TestClient, user):
    response = post_form_csrf_mismatch(
        client,
        LOGIN_PATH,
        {"email": user.email, "password": PASSWORD},
    )
    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert "access_token" not in response.cookies


def test_login_deactivated_user_rerenders(
    client: TestClient, deactivated_user,
):
    response = post_form(
        client,
        LOGIN_PATH,
        {"email": deactivated_user.email, "password": PASSWORD},
    )
    assert_form_invalid(response, contains=DEACTIVATED_MSG)
    assert "access_token" not in response.cookies


def test_login_temporary_user_rerenders_and_rolls_back_role(
    client: TestClient, session: SyncSession, temporary_user,
):
    response = post_form(
        client,
        LOGIN_PATH,
        {"email": temporary_user.email, "password": PASSWORD},
    )
    assert_form_invalid(response, contains=DEACTIVATED_MSG)
    assert "access_token" not in response.cookies

    session.expire_all()
    persisted = session.get_one(Q.user.select(id=temporary_user.id))
    assert persisted.role == UserRole.TEMPORARY
