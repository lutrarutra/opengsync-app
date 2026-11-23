import types

import pytest
from fastapi.testclient import TestClient
from opengsync_db import SyncSession, models, queries as Q

from server.core import dependencies

from ._http import post_form
from .test_audit_log import audit_records  # noqa: F401
from .test_share_routes import share_fixture


@pytest.fixture(autouse=True)
def frozen_rate_limit_clock(monkeypatch):
    """Freeze the rate-limit window so a test cannot straddle a period boundary.

    ``rate_limit`` derives its window from ``int(time.time()) // period``; without
    freezing, a slow loop (bcrypt logins) can roll over a minute mid-test and reset
    the counter, making the expected 429 non-deterministic.
    """
    monkeypatch.setattr(dependencies, "time", types.SimpleNamespace(time=lambda: 1_700_000_000.0))


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


def test_rate_limited_login_is_audited(
    client: TestClient,
    user: models.User,
    audit_records: list[dict],
):
    ip = "198.51.100.14"
    data = {"email": user.email, "password": "wrong-password"}
    for _ in range(21):
        response = post_form(client, "/htmx/auth/login", data, headers={"X-Real-IP": ip})
    assert response.status_code == 429

    record = audit_records[-1]
    assert record["status_code"] == 429
    assert record["route"] == "/htmx/auth/login"
    assert record["ip"] == ip
    assert record["user_id"] is None


def test_rate_limited_share_access_is_audited(client: TestClient, audit_records: list[dict]):
    ip = "198.51.100.15"
    path = "/api/webdav/not-a-real-token"
    for _ in range(201):
        response = client.get(path, headers={"X-Real-IP": ip})
    assert response.status_code == 429

    record = audit_records[-1]
    assert record["status_code"] == 429
    assert record["path"] == path
    assert record["ip"] == ip


def _redis(client: TestClient):
    from server.core import redis as rds
    return rds.RedisClient(client.app.state.redis_pool)  # type: ignore[attr-defined]


def test_valid_share_token_is_not_limited_while_requests_are_in_flight(
    client: TestClient,
    share_fixture,
):
    """Requests of a valid token count until they are answered: rclone's parallel requests (or users behind one
    NAT) can exceed the limit while they run. A recently validated token is let through anyway."""
    token = share_fixture.token.uuid
    ip = "198.51.100.14"
    url = f"/api/webdav/{token}/shared/root.txt"
    assert client.get(url, headers={"X-Real-IP": ip}).status_code == 200  # loads and caches the token

    window = int(1_700_000_000.0) // 60
    key = f"ratelimit:{ip}:/api/webdav/{{token}}/{{subpath:path}}:60:{window}"
    r = _redis(client)
    r.set(key, 10_000, ex=60)  # as if thousands of requests were still running
    try:
        assert client.get(url, headers={"X-Real-IP": ip}).status_code == 200
    finally:
        r.delete(key)


def test_unknown_share_token_over_the_limit_is_not_exempt(client: TestClient):
    ip = "198.51.100.15"
    path = "/api/shares/rclone/not-a-real-token"
    window = int(1_700_000_000.0) // 60
    key = f"ratelimit:{ip}:/api/shares/rclone/{{token}}:60:{window}"
    r = _redis(client)
    r.set(key, 10_000, ex=60)
    try:
        assert client.get(path, headers={"X-Real-IP": ip}).status_code == 429
    finally:
        r.delete(key)


def test_valid_share_request_deletes_its_rate_limit_counters(
    client: TestClient,
    share_fixture,
):
    token = share_fixture.token.uuid
    ip = "198.51.100.16"
    assert client.get(f"/api/webdav/{token}/shared/root.txt", headers={"X-Real-IP": ip}).status_code == 200
    r = _redis(client)
    assert r.get_keys(f"ratelimit:{ip}:*") == []
