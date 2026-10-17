"""ChangePasswordForm: authorization, validation, persistence, and sessions."""

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
    set_cookie_header,
)

PATH = "/htmx/auth/change-password"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"
CURRENT_PASSWORD_MSG = "Current password is incorrect."
MISMATCH_MSG = "New passwords do not match."


def _payload(
    current_password: str = PASSWORD,
    new_password: str = "new-password1",
    confirm_new_password: str = "new-password1",
) -> dict[str, str]:
    return {
        "current_password": current_password,
        "new_password": new_password,
        "confirm_new_password": confirm_new_password,
    }


def _change(
    client: TestClient,
    data: dict[str, str] | None = None,
    *,
    token: str | None = None,
    user_id: int | None = None,
):
    return post_form(
        client,
        PATH,
        data or _payload(),
        token=token,
        params={"user_id": user_id} if user_id is not None else None,
    )


def test_change_password_get_renders_form(client: TestClient, user_token: str):
    response = get(client, PATH, token=user_token)

    assert response.status_code == 200
    assert 'name="current_password"' in response.text
    assert 'name="new_password"' in response.text
    assert 'name="confirm_new_password"' in response.text
    assert 'name="csrf_token"' in response.text


def test_change_password_anonymous_user_is_redirected_to_login(client: TestClient):
    response = get(client, PATH)

    assert response.status_code == 303
    assert "/auth/login" in response.headers["location"]


def test_change_password_user_cannot_access_another_user(
    client: TestClient, user_token: str, user_2,
):
    response = get(
        client,
        PATH,
        token=user_token,
        params={"user_id": user_2.id},
    )

    assert response.status_code == 403
    assert "permission" in response.text.lower()


def test_admin_can_render_another_users_change_password_form(
    client: TestClient, admin_token: str, user,
):
    response = get(
        client,
        PATH,
        token=admin_token,
        params={"user_id": user.id},
    )

    assert response.status_code == 200
    assert 'name="current_password"' in response.text


def test_change_password_valid_self_change_persists_and_redirects(
    client: TestClient, session: SyncSession, user, user_token: str,
):
    new_password = "new-password1"
    response = _change(
        client,
        _payload(new_password=new_password),
        token=user_token,
        user_id=user.id,
    )

    assert_htmx_redirect(response, contains="/auth/login")
    assert_flash(response, "Password Changed, please log-in!", category="success")
    cookies = set_cookie_header(response)
    assert "access_token=" in cookies
    assert "csrf_token=" in cookies
    assert "Max-Age=0" in cookies

    session.expire_all()
    changed = session.get_one(Q.user.select(id=user.id))
    from server.core.secrets import BcryptCompat

    bcrypt = BcryptCompat()
    assert changed.pw_set_datetime is not None
    assert bcrypt.check_password_hash(changed.password, new_password)
    assert not bcrypt.check_password_hash(changed.password, PASSWORD)


def test_change_password_admin_can_change_another_user(
    client: TestClient, session: SyncSession, admin_token: str, user,
):
    new_password = "admin-set-password1"
    response = _change(
        client,
        _payload(
            new_password=new_password,
            confirm_new_password=new_password,
        ),
        token=admin_token,
        user_id=user.id,
    )

    assert_htmx_redirect(response, contains=f"/users/{user.id}")
    assert_flash(response, "Password Changed!", category="success")

    session.expire_all()
    changed = session.get_one(Q.user.select(id=user.id))
    from server.core.secrets import BcryptCompat

    assert BcryptCompat().check_password_hash(changed.password, new_password)


def test_change_password_wrong_current_password_rerenders(
    client: TestClient, session: SyncSession, user, user_token: str,
):
    response = _change(
        client,
        _payload(current_password="wrong-password"),
        token=user_token,
        user_id=user.id,
    )

    assert_form_invalid(response, contains=CURRENT_PASSWORD_MSG)
    session.expire_all()
    persisted = session.get_one(Q.user.select(id=user.id))
    from server.core.secrets import BcryptCompat

    assert BcryptCompat().check_password_hash(persisted.password, PASSWORD)


def test_change_password_mismatch_rerenders(
    client: TestClient, session: SyncSession, user, user_token: str,
):
    response = _change(
        client,
        _payload(confirm_new_password="different-password"),
        token=user_token,
        user_id=user.id,
    )

    assert_form_invalid(response, contains=MISMATCH_MSG)
    session.expire_all()
    persisted = session.get_one(Q.user.select(id=user.id))
    from server.core.secrets import BcryptCompat

    assert BcryptCompat().check_password_hash(persisted.password, PASSWORD)


def test_change_password_short_new_password_rerenders(
    client: TestClient, session: SyncSession, user, user_token: str,
):
    response = _change(
        client,
        _payload(new_password="short", confirm_new_password="short"),
        token=user_token,
    )

    assert_form_invalid(response)
    assert "at least 8" in response.text
    session.expire_all()
    persisted = session.get_one(Q.user.select(id=user.id))
    from server.core.secrets import BcryptCompat

    assert BcryptCompat().check_password_hash(persisted.password, PASSWORD)


def test_change_password_missing_fields_rerenders(
    client: TestClient, user_token: str,
):
    response = _change(
        client,
        {
            "current_password": "",
            "new_password": "",
            "confirm_new_password": "",
        },
        token=user_token,
    )

    assert_form_invalid(response)
    assert "Current Password is required" in response.text
    assert "New Password is required" in response.text
    assert "Confirm New Password is required" in response.text


def test_change_password_csrf_mismatch_rerenders(
    client: TestClient, user_token: str,
):
    response = post_form_csrf_mismatch(
        client,
        PATH,
        _payload(),
        token=user_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")


def test_change_password_revokes_previous_access_token(
    client: TestClient, user, user_token: str,
):
    response = _change(client, token=user_token, user_id=user.id)
    assert_htmx_redirect(response, contains="/auth/login")

    dashboard = get(client, "/", token=user_token)
    assert dashboard.status_code == 303
    assert "/auth/login" in dashboard.headers.get("location", "")
