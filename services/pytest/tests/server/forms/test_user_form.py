"""UserForm: edit — rendering, permissions, role/email gating, and persistence.

The form is edit-only (users are created via registration).  Access control:
- **Owner** → WRITE: can edit name, cannot change role or email.
- **Insider** → INSIDER: can edit name, cannot change role or email.
- **Admin** → ADMIN: can edit name, role, and email.
- **Stranger** → NONE: denied.
"""

import datetime as dt

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from .._profile import new_profile_payload, set_profile, INSTITUTE, DEPARTMENT, PI_NAME, PI_EMAIL
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

EDIT = "/htmx/users/{user_id}/edit"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _edit_path(user_id: int) -> str:
    return EDIT.format(user_id=user_id)


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "first_name": "Updated",
        "last_name": "User",
        "email": "updated@example.com",
        "role": str(C.UserRole.CLIENT.id),
        **new_profile_payload(),
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _reload(session: SyncSession, user: models.User) -> models.User:
    session.expire_all()
    return session.get_one(Q.user.select(id=user.id))


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_edit_form_get_renders_for_owner(
    client: TestClient,
    user,
    user_token: str,
):
    response = get(client, _edit_path(user.id), user_token)

    assert response.status_code == 200
    assert user.first_name in response.text
    assert user.last_name in response.text
    assert 'name="first_name"' in response.text
    assert 'name="last_name"' in response.text
    assert 'name="role"' in response.text
    assert 'name="csrf_token"' in response.text


def test_edit_form_get_denied_for_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    response = get(client, _edit_path(user.id), user_2_token)

    assert response.status_code == 403


def test_edit_form_get_unknown_user_is_404(
    client: TestClient,
    user_token: str,
):
    assert get(client, _edit_path(999999), user_token).status_code == 404


# ── Edit (POST) — permissions ───────────────────────────────────────────────


def test_edit_owner_can_change_name(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form(
        client,
        _edit_path(user.id),
        _payload(first_name="NewFirst", last_name="NewLast", email=user.email),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/users/{user.id}")
    assert_flash(response, "Changes Saved!", category="success")

    updated = _reload(session, user)
    assert updated.first_name == "NewFirst"
    assert updated.last_name == "NewLast"


def test_edit_owner_cannot_change_role(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    original_role = user.role
    response = post_form(
        client,
        _edit_path(user.id),
        _payload(role=str(C.UserRole.TECHNICIAN.id)),
        token=user_token,
    )

    assert_form_invalid(response)
    assert _reload(session, user).role == original_role


def test_edit_owner_cannot_change_email(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    original_email = user.email
    response = post_form(
        client,
        _edit_path(user.id),
        _payload(email="hijacked@example.com"),
        token=user_token,
    )

    assert_form_invalid(response)
    assert _reload(session, user).email == original_email


def test_edit_denied_for_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    response = post_form(
        client,
        _edit_path(user.id),
        _payload(first_name="Hijacked"),
        token=user_2_token,
    )

    assert response.status_code == 403
    assert _reload(session, user).first_name != "Hijacked"


def test_edit_unknown_user_is_404(
    client: TestClient,
    user_token: str,
):
    response = post_form(
        client,
        _edit_path(999999),
        _payload(first_name="Ghost"),
        token=user_token,
    )

    assert response.status_code == 404


# ── Edit (POST) — insider ───────────────────────────────────────────────────


def test_edit_insider_can_change_name(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    response = post_form(
        client,
        _edit_path(user.id),
        _payload(first_name="InsiderUpdated", last_name="InsiderUpdated", email=user.email),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/users/{user.id}")
    assert_flash(response, "Changes Saved!", category="success")

    updated = _reload(session, user)
    assert updated.first_name == "InsiderUpdated"


def test_edit_insider_cannot_change_role(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    original_role = user.role
    response = post_form(
        client,
        _edit_path(user.id),
        _payload(role=str(C.UserRole.ADMIN.id)),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert _reload(session, user).role == original_role


def test_edit_insider_cannot_change_email(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    original_email = user.email
    response = post_form(
        client,
        _edit_path(user.id),
        _payload(email="insider-changed@example.com"),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert _reload(session, user).email == original_email


# ── Edit (POST) — admin ─────────────────────────────────────────────────────


def test_edit_admin_can_change_name(
    client: TestClient,
    session: SyncSession,
    user,
    admin_token: str,
):
    response = post_form(
        client,
        _edit_path(user.id),
        _payload(first_name="AdminUpdated", last_name="AdminUpdated", email=user.email),
        token=admin_token,
    )

    assert_htmx_redirect(response, f"/users/{user.id}")
    assert_flash(response, "Changes Saved!", category="success")

    updated = _reload(session, user)
    assert updated.first_name == "AdminUpdated"


def test_edit_admin_can_change_role(
    client: TestClient,
    session: SyncSession,
    user,
    admin_token: str,
):
    response = post_form(
        client,
        _edit_path(user.id),
        _payload(role=str(C.UserRole.BIOINFORMATICIAN.id)),
        token=admin_token,
    )

    assert_htmx_redirect(response, f"/users/{user.id}")

    updated = _reload(session, user)
    assert updated.role == C.UserRole.BIOINFORMATICIAN


def test_edit_admin_reactivating_user_restarts_inactivity_window(
    client: TestClient,
    session: SyncSession,
    user,
    admin_token: str,
):
    user.role = C.UserRole.DEACTIVATED
    user.last_login = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=400)
    session.commit()

    response = post_form(client, _edit_path(user.id), _payload(), token=admin_token)

    assert_htmx_redirect(response, f"/users/{user.id}")
    updated = _reload(session, user)
    assert updated.role == C.UserRole.CLIENT
    assert updated.last_login > dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)


def test_edit_admin_role_change_keeps_last_login(
    client: TestClient,
    session: SyncSession,
    user,
    admin_token: str,
):
    assert user.last_login is None

    post_form(client, _edit_path(user.id), _payload(role=str(C.UserRole.TECHNICIAN.id)), token=admin_token)

    updated = _reload(session, user)
    assert updated.role == C.UserRole.TECHNICIAN
    assert updated.last_login is None


def test_edit_admin_can_change_email(
    client: TestClient,
    session: SyncSession,
    user,
    admin_token: str,
):
    new_email = "admin-changed@example.com"
    response = post_form(
        client,
        _edit_path(user.id),
        _payload(email=new_email),
        token=admin_token,
    )

    assert_htmx_redirect(response, f"/users/{user.id}")

    updated = _reload(session, user)
    assert updated.email == new_email


# ── Edit (POST) — CSRF ──────────────────────────────────────────────────────


def test_edit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form_csrf_mismatch(
        client,
        _edit_path(user.id),
        _payload(first_name="CSRF_User"),
        token=user_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert _reload(session, user).first_name != "CSRF_User"

# ── Organization & PI ───────────────────────────────────────────────────────

_NO_PROFILE = {key: "" for key in new_profile_payload()}


def _profile(user: models.User) -> tuple:
    return (user.institute, user.department, user.pi_name, user.pi_email)


def test_edit_form_get_prefills_profile(client: TestClient, session: SyncSession, user, user_token: str):
    set_profile(session, user)
    session.commit()

    response = get(client, _edit_path(user.id), user_token)

    assert response.status_code == 200
    for value in (INSTITUTE, DEPARTMENT, PI_NAME):
        assert value in response.text
    # PI emails are not shown to customers (the key is a hash)
    assert PI_EMAIL not in response.text


def test_edit_owner_saves_profile(client: TestClient, session: SyncSession, user, user_token: str):
    response = post_form(client, _edit_path(user.id), _payload(email=user.email), token=user_token)

    assert_htmx_redirect(response)
    assert _profile(_reload(session, user)) == (INSTITUTE, DEPARTMENT, PI_NAME, PI_EMAIL)


def test_edit_owner_customer_must_give_profile(client: TestClient, session: SyncSession, user, user_token: str):
    response = post_form(
        client, _edit_path(user.id), _payload(email=user.email, first_name="Changed", **_NO_PROFILE), token=user_token,
    )

    assert_form_invalid(response, contains="Institute is required.")
    assert _reload(session, user).first_name != "Changed"


def test_edit_insider_may_leave_customer_profile_empty(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    response = post_form(
        client, _edit_path(user.id), _payload(email=user.email, first_name="Changed", **_NO_PROFILE),
        token=insider_token,
    )

    assert_htmx_redirect(response)
    reloaded = _reload(session, user)
    assert reloaded.first_name == "Changed"
    assert _profile(reloaded) == (None, None, None, None)


def test_edit_insider_may_clear_customer_profile(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    set_profile(session, user)
    session.commit()

    response = post_form(client, _edit_path(user.id), _payload(email=user.email, **_NO_PROFILE), token=insider_token)

    assert_htmx_redirect(response)
    assert _profile(_reload(session, user)) == (None, None, None, None)


def test_edit_owner_cannot_clear_profile(client: TestClient, session: SyncSession, user, user_token: str):
    set_profile(session, user, department=None)
    session.commit()

    response = post_form(
        client, _edit_path(user.id), _payload(email=user.email, **{"institute": "", "institute-text": ""}),
        token=user_token,
    )

    assert_form_invalid(response, contains="Institute is required.")
    assert _reload(session, user).institute == INSTITUTE


def test_edit_owner_insider_profile_is_optional(
    client: TestClient, session: SyncSession, insider, insider_token: str,
):
    response = post_form(
        client, _edit_path(insider.id),
        _payload(email=insider.email, role=str(insider.role.id), **_NO_PROFILE), token=insider_token,
    )

    assert_htmx_redirect(response)


def test_edit_form_email_read_only_except_for_admin(
    client: TestClient, user, user_token: str, admin_token: str,
):
    import re

    def email_input(token: str) -> str:
        text = get(client, _edit_path(user.id), token).text
        match = re.search(r'<input[^>]*name="email"[^>]*>', text, re.S)
        assert match is not None
        return match.group(0)

    assert "readonly" in email_input(user_token)
    assert "readonly" not in email_input(admin_token)
