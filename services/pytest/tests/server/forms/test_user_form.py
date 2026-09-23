"""UserForm: edit — rendering, permissions, role/email gating, and persistence.

The form is edit-only (users are created via registration).  Access control:
- **Owner** → WRITE: can edit name, cannot change role or email.
- **Insider** → INSIDER: can edit name, cannot change role or email.
- **Admin** → ADMIN: can edit name, role, and email.
- **Stranger** → NONE: denied.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

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