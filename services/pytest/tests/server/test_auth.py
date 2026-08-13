from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_help_is_public(client: TestClient):
    response = client.get("/help")
    assert response.status_code not in (303, 401, 403)


def test_dashboard_requires_authentication(client: TestClient):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert "/auth/login" in response.headers.get("location", "")


def test_login_page_is_public(client: TestClient):
    response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code not in (303, 401, 403)


def test_login_rejects_invalid_credentials(client: TestClient, user):
    client.cookies.set("csrf_token", "test-csrf")
    response = client.post(
        "/htmx/auth/login",
        data={
            "email": user.email,
            "password": "wrong-password",
            "csrf_token": "test-csrf",
        },
    )
    assert response.status_code == 409


def test_login_sets_access_token(client: TestClient, user):
    client.cookies.set("csrf_token", "test-csrf")
    response = client.post(
        "/htmx/auth/login",
        data={
            "email": user.email,
            "password": "testpassword",
            "csrf_token": "test-csrf",
        },
        follow_redirects=False,
    )
    assert response.status_code in (200, 204, 303)
    assert "access_token" in response.cookies or "access_token" in response.headers.get("set-cookie", "")


def test_dashboard_with_user_token(client: TestClient, user_token: str):
    response = client.get("/", headers=_auth(user_token), follow_redirects=False)
    assert response.status_code not in (303, 401, 403)
