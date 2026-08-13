"""Role gating for the FastAPI server: client vs insider vs admin."""

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _allowed(response) -> None:
    assert response.status_code not in (303, 401, 403)


# --- unauthenticated ---

def test_projects_requires_authentication(client: TestClient):
    response = client.get("/projects/", follow_redirects=False)
    assert response.status_code == 303


def test_users_page_requires_authentication(client: TestClient):
    response = client.get("/users/", follow_redirects=False)
    assert response.status_code == 303


def test_experiments_requires_authentication(client: TestClient):
    response = client.get("/experiments/", follow_redirects=False)
    assert response.status_code == 303


def test_admin_requires_authentication(client: TestClient):
    response = client.get("/admin/", follow_redirects=False)
    assert response.status_code == 303


# --- client (regular user) ---

def test_user_can_access_projects(client: TestClient, user_token: str):
    _allowed(client.get("/projects/", headers=_auth(user_token), follow_redirects=False))


def test_user_cannot_access_users_page(client: TestClient, user_token: str):
    response = client.get("/users/", headers=_auth(user_token), follow_redirects=False)
    assert response.status_code == 403


def test_user_cannot_access_experiments(client: TestClient, user_token: str):
    response = client.get("/experiments/", headers=_auth(user_token), follow_redirects=False)
    assert response.status_code == 403


def test_user_cannot_access_admin(client: TestClient, user_token: str):
    response = client.get("/admin/", headers=_auth(user_token), follow_redirects=False)
    assert response.status_code == 403


# --- insider ---

def test_insider_can_access_projects(client: TestClient, insider_token: str):
    _allowed(client.get("/projects/", headers=_auth(insider_token), follow_redirects=False))


def test_insider_can_access_users_page(client: TestClient, insider_token: str):
    _allowed(client.get("/users/", headers=_auth(insider_token), follow_redirects=False))


def test_insider_can_access_experiments(client: TestClient, insider_token: str):
    _allowed(client.get("/experiments/", headers=_auth(insider_token), follow_redirects=False))


def test_insider_cannot_access_admin(client: TestClient, insider_token: str):
    response = client.get("/admin/", headers=_auth(insider_token), follow_redirects=False)
    assert response.status_code == 403


# --- admin ---

def test_admin_can_access_projects(client: TestClient, admin_token: str):
    _allowed(client.get("/projects/", headers=_auth(admin_token), follow_redirects=False))


def test_admin_can_access_users_page(client: TestClient, admin_token: str):
    _allowed(client.get("/users/", headers=_auth(admin_token), follow_redirects=False))


def test_admin_can_access_experiments(client: TestClient, admin_token: str):
    _allowed(client.get("/experiments/", headers=_auth(admin_token), follow_redirects=False))


def test_admin_can_access_admin_page(client: TestClient, admin_token: str):
    _allowed(client.get("/admin/", headers=_auth(admin_token), follow_redirects=False))
