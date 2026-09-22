"""APITokenForm: rendering, creation, deactivation, ownership, and CSRF."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q, models

from ..._http import (
    assert_flash,
    assert_form_invalid,
    get,
    post_form,
    post_form_csrf_mismatch,
)

BEGIN_PATH = "/htmx/users/{user_id}/create-api-token"
DEACTIVATE_PATH = "/htmx/api-tokens/{token_id}/deactivate"
TABLE_PATH = "/htmx/api-tokens/render-table-page"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"
DEFAULT_TIME_VALID_MIN = 60 * 24 * 365


def _begin_path(user_id: int) -> str:
    return BEGIN_PATH.format(user_id=user_id)


def _deactivate_path(token_id: int) -> str:
    return DEACTIVATE_PATH.format(token_id=token_id)


def _create_token(session: SyncSession, owner: models.User, time_valid_min: int = 60) -> models.APIToken:
    token = session.save(Q.api_token.create(owner=owner, time_valid_min=time_valid_min), flush=True)
    session.commit()
    return token


def _owner_tokens(session: SyncSession, owner_id: int) -> list[models.APIToken]:
    session.expire_all()
    return session.get_all(Q.api_token.select(owner_id=owner_id), limit=None)


def test_create_api_token_get_renders_form(client: TestClient, user_token: str, user):
    response = get(client, _begin_path(user.id), user_token)

    assert response.status_code == 200
    assert 'name="time_valid_min"' in response.text
    assert 'name="csrf_token"' in response.text
    assert "1 Year" in response.text
    assert "30 Days" in response.text


def test_create_api_token_anonymous_is_redirected_to_login(client: TestClient, user):
    response = get(client, _begin_path(user.id))

    assert response.status_code == 303
    assert "/auth/login" in response.headers["location"]


def test_create_api_token_unknown_user_is_404(client: TestClient, user_token: str):
    response = get(client, _begin_path(999999), user_token)

    assert response.status_code == 404


def test_create_api_token_persists_and_shows_value_once(
    client: TestClient,
    session: SyncSession,
    user_token: str,
    user,
):
    response = post_form(
        client,
        _begin_path(user.id),
        {"time_valid_min": str(60 * 24 * 90)},
        token=user_token,
    )

    assert response.status_code == 200
    assert_flash(response, "API Token Created!", category="success")

    tokens = _owner_tokens(session, user.id)
    assert len(tokens) == 1
    token = tokens[0]
    assert token.time_valid_min == 60 * 24 * 90
    assert not token.is_expired
    # The generated token value is shown once in the completion template.
    assert token.uuid in response.text
    assert len(token.uuid) == 36


def test_create_api_token_uses_default_validity(
    client: TestClient,
    session: SyncSession,
    user_token: str,
    user,
):
    response = post_form(client, _begin_path(user.id), {}, token=user_token)

    assert response.status_code == 200
    tokens = _owner_tokens(session, user.id)
    assert len(tokens) == 1
    assert tokens[0].time_valid_min == DEFAULT_TIME_VALID_MIN


def test_create_api_token_invalid_validity_rerenders(
    client: TestClient,
    session: SyncSession,
    user_token: str,
    user,
):
    response = post_form(
        client,
        _begin_path(user.id),
        {"time_valid_min": "not-a-number"},
        token=user_token,
    )

    assert_form_invalid(response)
    assert _owner_tokens(session, user.id) == []


def test_create_api_token_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user_token: str,
    user,
):
    response = post_form_csrf_mismatch(
        client,
        _begin_path(user.id),
        {"time_valid_min": str(60 * 24 * 30)},
        token=user_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert _owner_tokens(session, user.id) == []


def test_user_cannot_create_token_for_another_user(
    client: TestClient,
    session: SyncSession,
    user_token: str,
    user_2,
):
    response = post_form(
        client,
        _begin_path(user_2.id),
        {"time_valid_min": str(60 * 24 * 30)},
        token=user_token,
    )

    assert response.status_code == 403
    assert _owner_tokens(session, user_2.id) == []


def test_admin_can_create_token_for_another_user(
    client: TestClient,
    session: SyncSession,
    admin_token: str,
    user,
):
    response = post_form(
        client,
        _begin_path(user.id),
        {"time_valid_min": str(60 * 24 * 30)},
        token=admin_token,
    )

    assert response.status_code == 200
    tokens = _owner_tokens(session, user.id)
    assert len(tokens) == 1
    assert tokens[0].time_valid_min == 60 * 24 * 30


def test_deactivate_active_token(
    client: TestClient,
    session: SyncSession,
    user_token: str,
    user,
):
    token = _create_token(session, user)

    response = post_form(client, _deactivate_path(token.id), {}, token=user_token)

    assert response.status_code == 204
    assert_flash(response, "API token deactivated.", category="success")

    session.expire_all()
    assert session.get_one(Q.api_token.select(id=token.id))._expired is True


def test_deactivate_already_inactive_token(
    client: TestClient,
    session: SyncSession,
    user_token: str,
    user,
):
    token = _create_token(session, user)
    token._expired = True
    session.commit()

    response = post_form(client, _deactivate_path(token.id), {}, token=user_token)

    assert response.status_code == 204
    session.expire_all()
    assert session.get_one(Q.api_token.select(id=token.id))._expired is True


def test_user_cannot_deactivate_another_users_token(
    client: TestClient,
    session: SyncSession,
    user_token: str,
    user_2,
):
    token = _create_token(session, user_2)

    response = post_form(client, _deactivate_path(token.id), {}, token=user_token)

    assert response.status_code == 403
    session.expire_all()
    assert session.get_one(Q.api_token.select(id=token.id))._expired is False


def test_admin_can_deactivate_another_users_token(
    client: TestClient,
    session: SyncSession,
    admin_token: str,
    user,
):
    token = _create_token(session, user)

    response = post_form(client, _deactivate_path(token.id), {}, token=admin_token)

    assert response.status_code == 204
    session.expire_all()
    assert session.get_one(Q.api_token.select(id=token.id))._expired is True


def test_deactivate_unknown_token_is_404(client: TestClient, user_token: str):
    response = post_form(client, _deactivate_path(999999), {}, token=user_token)

    assert response.status_code == 404


def test_token_table_requires_insider_without_owner_filter(
    client: TestClient,
    user_token: str,
    insider_token: str,
):
    assert get(client, TABLE_PATH, user_token).status_code == 403
    assert get(client, TABLE_PATH, insider_token).status_code == 200


def test_user_can_view_own_token_table(
    client: TestClient,
    session: SyncSession,
    user_token: str,
    user,
):
    token = _create_token(session, user)

    response = get(client, TABLE_PATH, user_token, params={"owner_id": user.id})

    assert response.status_code == 200
    assert f"/api-tokens/{token.id}/deactivate" in response.text


def test_user_cannot_view_another_users_token_table(
    client: TestClient,
    session: SyncSession,
    user_token: str,
    user_2,
):
    _create_token(session, user_2)

    response = get(client, TABLE_PATH, user_token, params={"owner_id": user_2.id})

    assert response.status_code == 403


def test_insider_can_view_another_users_token_table(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
    user,
):
    token = _create_token(session, user)

    response = get(client, TABLE_PATH, insider_token, params={"owner_id": user.id})

    assert response.status_code == 200
    assert f"/api-tokens/{token.id}/deactivate" in response.text