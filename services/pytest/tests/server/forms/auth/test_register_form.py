"""RegisterForm: GET rendering, role/domain checks, CSRF, and mail/redirect behavior."""

import pytest

from opengsync_db import SyncSession, queries as Q
from opengsync_db.categories import UserRole

from ..._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    OpenGSyncTestClient,
    post_form,
    post_form_csrf_mismatch,
)

REGISTER_PATH = "/htmx/auth/register"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"
DOMAIN_MSG = "Specified email domain is not found in white-list. Please contact us."
ROLE_PERM_MSG = "You don't have permissions to create user with this role"


class FailingMailer:
    def send_welcome_back(self, recipient_email: str):
        raise RuntimeError("smtp down")

    def send_registration(self, recipient_email: str, verification_link):
        raise RuntimeError("smtp down")


def _register(client: OpenGSyncTestClient, email: str, role: int | None = None, token: str | None = None):
    data: dict[str, object] = {"email": email}
    if role is not None:
        data["role"] = str(role)
    return post_form(client, REGISTER_PATH, data, token=token)


def test_register_get_renders_form(client: OpenGSyncTestClient):
    response = get(client, REGISTER_PATH)
    assert response.status_code == 200
    assert 'name="email"' in response.text
    assert 'name="csrf_token"' in response.text
    assert 'name="role"' not in response.text


def test_register_get_insider_includes_role(client: OpenGSyncTestClient, insider_token: str):
    response = get(client, REGISTER_PATH, token=insider_token)
    assert response.status_code == 200
    assert 'name="email"' in response.text
    assert 'name="role"' in response.text


def test_register_new_email_sends_welcome_back(
    client: OpenGSyncTestClient, fake_mailer, session: SyncSession,
):
    email = "new-user@example.com"

    response = _register(client, email)

    assert_htmx_redirect(response, contains="/auth/login")
    assert fake_mailer.welcome_back == [email]
    assert fake_mailer.registration == []
    assert session.first(Q.user.select(email=email)) is None


def test_register_existing_email_sends_registration_link(
    client: OpenGSyncTestClient, fake_mailer, session: SyncSession, user,
):
    before = session.count(Q.user.select())

    response = _register(client, user.email)

    assert_htmx_redirect(response, contains="/auth/login")
    assert fake_mailer.welcome_back == []
    assert len(fake_mailer.registration) == 1
    sent_email, link = fake_mailer.registration[0]
    assert sent_email == user.email
    assert "/auth/complete-registration/" in link
    assert session.count(Q.user.select()) == before


def test_register_invalid_email_rerenders(client: OpenGSyncTestClient, fake_mailer, session: SyncSession):
    response = _register(client, "not-an-email")
    assert_form_invalid(response)
    assert fake_mailer.welcome_back == []
    assert fake_mailer.registration == []
    assert session.first(Q.user.select(email="not-an-email")) is None


def test_register_missing_email_rerenders(client: OpenGSyncTestClient):
    response = post_form(client, REGISTER_PATH, {"email": ""})
    assert_form_invalid(response, contains="Email is required")


def test_register_csrf_mismatch_rerenders(client: OpenGSyncTestClient, fake_mailer):
    response = post_form_csrf_mismatch(
        client,
        REGISTER_PATH,
        {"email": "new-user@example.com"},
    )
    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert fake_mailer.welcome_back == []
    assert fake_mailer.registration == []


def test_register_domain_not_whitelisted_rerenders(client: OpenGSyncTestClient, fake_mailer):
    from server.core import config

    original = list(config.settings.app_config.email_domain_white_list)
    config.settings.app_config.email_domain_white_list[:] = ["allowed.org"]
    try:
        response = _register(client, "user@example.com")
        assert_form_invalid(response, contains=DOMAIN_MSG)
        assert fake_mailer.welcome_back == []
    finally:
        config.settings.app_config.email_domain_white_list[:] = original


def test_register_whitelisted_domain_succeeds(client: OpenGSyncTestClient, fake_mailer):
    from server.core import config

    original = list(config.settings.app_config.email_domain_white_list)
    config.settings.app_config.email_domain_white_list[:] = ["example.com"]
    try:
        response = _register(client, "user@example.com")
        assert_htmx_redirect(response, contains="/auth/login")
        assert fake_mailer.welcome_back == ["user@example.com"]
    finally:
        config.settings.app_config.email_domain_white_list[:] = original


def test_register_insider_bypasses_domain_whitelist(
    client: OpenGSyncTestClient, fake_mailer, insider_token: str,
):
    from server.core import config

    original = list(config.settings.app_config.email_domain_white_list)
    config.settings.app_config.email_domain_white_list[:] = ["allowed.org"]
    try:
        response = _register(
            client, "user@example.com", role=UserRole.CLIENT.id, token=insider_token,
        )
        assert_htmx_redirect(response, contains="/auth/login")
        assert fake_mailer.welcome_back == ["user@example.com"]
    finally:
        config.settings.app_config.email_domain_white_list[:] = original


def test_register_anonymous_cannot_choose_admin_role(client: OpenGSyncTestClient, fake_mailer):
    response = _register(client, "user@example.com", role=UserRole.ADMIN.id)
    # The role field is hidden for anonymous users, so its error is not part
    # of the rendered fragment. The 202 response and lack of mail prove that
    # the permission branch rejected the request.
    assert_form_invalid(response)
    assert fake_mailer.welcome_back == []


def test_register_technician_cannot_choose_admin_role(
    client: OpenGSyncTestClient, fake_mailer, insider_token: str,
):
    response = _register(client, "user@example.com", role=UserRole.ADMIN.id, token=insider_token,)
    assert_form_invalid(response, contains=ROLE_PERM_MSG)
    assert fake_mailer.welcome_back == []


def test_register_technician_can_request_deactivated(
    client: OpenGSyncTestClient, fake_mailer, insider_token: str,
):
    response = _register(
        client, "user@example.com", role=UserRole.DEACTIVATED.id, token=insider_token,
    )
    assert_htmx_redirect(response, contains="/auth/login")
    assert fake_mailer.welcome_back == ["user@example.com"]


def test_register_invalid_role_rerenders(client: OpenGSyncTestClient, fake_mailer, insider_token: str):
    response = _register(client, "user@example.com", role=99, token=insider_token)
    assert_form_invalid(response, contains="Invalid role.")
    assert fake_mailer.welcome_back == []


def test_register_mailer_failure_does_not_create_user(
    client: OpenGSyncTestClient, session: SyncSession,
):
    client.app.state.mailer = FailingMailer()
    email = "new-user@example.com"

    with pytest.raises(RuntimeError, match="smtp down"):
        _register(client, email)

    assert session.first(Q.user.select(email=email)) is None
