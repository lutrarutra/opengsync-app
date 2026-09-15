from fastapi.testclient import TestClient
from opengsync_db import SyncSession, models, queries as Q

from ._http import post_form
from .test_share_routes import share_fixture


def test_login_rate_limit(
    client: TestClient,
    user: models.User,
):
    ip = "198.51.100.10"
    data = {"email": user.email, "password": "wrong-password"}

    responses = [
        post_form(client, "/htmx/auth/login", data, headers={"X-Real-IP": ip})
        for _ in range(20)
    ]

    assert all(response.status_code == 202 for response in responses)
    assert post_form(
        client,
        "/htmx/auth/login",
        data,
        headers={"X-Real-IP": ip},
    ).status_code == 429


def test_invalid_share_token_is_rate_limited(client: TestClient):
    ip = "198.51.100.11"
    path = "/api/webdav/not-a-real-token"

    responses = [
        client.get(path, headers={"X-Real-IP": ip})
        for _ in range(200)
    ]

    assert all(response.status_code == 404 for response in responses)
    assert client.get(path, headers={"X-Real-IP": ip}).status_code == 429


def test_valid_share_token_clears_rate_limit(
    client: TestClient,
    share_fixture,
):
    token = share_fixture.token.uuid
    ip = "198.51.100.12"

    responses = [
        client.get(
            f"/api/webdav/{token}/shared/root.txt",
            headers={"X-Real-IP": ip},
        )
        for _ in range(25)
    ]

    assert all(response.status_code == 200 for response in responses)


def test_expired_share_token_remains_rate_limited(
    client: TestClient,
    session: SyncSession,
    user: models.User,
):
    token = session.save(
        Q.share_token.create(owner=user, time_valid_min=60, paths=["shared"]),
        flush=True,
    )
    token._expired = True
    session.save(token)
    session.commit()

    ip = "198.51.100.13"
    path = f"/api/webdav/{token.uuid}/shared"
    responses = [
        client.get(path, headers={"X-Real-IP": ip})
        for _ in range(200)
    ]

    assert all(response.status_code == 403 for response in responses)
    assert client.get(path, headers={"X-Real-IP": ip}).status_code == 429
