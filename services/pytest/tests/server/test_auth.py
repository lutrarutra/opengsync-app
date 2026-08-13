from fastapi.testclient import TestClient

from ._http import auth, get, post_form


def _public(response) -> None:
    assert response.status_code not in (303, 401, 403)


def test_health(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_help_is_public(client: TestClient):
    _public(client.get("/help", follow_redirects=False))


def test_dashboard_requires_authentication(client: TestClient):
    response = get(client, "/")
    assert response.status_code == 303
    assert "/auth/login" in response.headers.get("location", "")


def test_login_page_is_public(client: TestClient):
    _public(get(client, "/auth/login"))


def test_login_form_is_public(client: TestClient):
    _public(get(client, "/htmx/auth/login"))


def test_register_form_is_public(client: TestClient):
    _public(get(client, "/htmx/auth/register"))


def test_complete_registration_page_is_public(client: TestClient):
    _public(get(client, "/auth/complete-registration/not-a-real-token"))


def test_reset_password_page_is_public(client: TestClient):
    _public(get(client, "/auth/reset-password", params={"token": "not-a-real-token"}))


def test_logout_requires_authentication(client: TestClient):
    response = client.post("/htmx/auth/logout", follow_redirects=False)
    assert response.status_code == 303
    assert "/auth/login" in response.headers.get("location", "")


def test_login_rejects_invalid_credentials(client: TestClient, user):
    response = post_form(
        client,
        "/htmx/auth/login",
        {"email": user.email, "password": "wrong-password"},
    )
    assert response.status_code == 200


def test_login_sets_access_token(client: TestClient, user):
    response = post_form(
        client,
        "/htmx/auth/login",
        {"email": user.email, "password": "testpassword"},
    )
    assert response.status_code in (200, 204, 303)
    assert "access_token" in response.cookies or "access_token" in response.headers.get("set-cookie", "")


def test_dashboard_with_user_token(client: TestClient, user_token: str):
    response = client.get("/", headers=auth(user_token), follow_redirects=False)
    assert response.status_code not in (303, 401, 403)
