import json
from typing import Any

from fastapi.testclient import TestClient
from starlette.testclient import _WrapASGI2
from starlette.datastructures import State
from redis import ConnectionPool

from opengsync_db import SyncDBHandler

CSRF = "test-csrf"

class AppState(State):
    db_handler: SyncDBHandler
    redis_pool: ConnectionPool

class App(_WrapASGI2):
    state: AppState

class OpenGSyncTestClient(TestClient):
    app: App


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def flush_redis(client: OpenGSyncTestClient) -> None:
    from redis import Redis
    Redis(connection_pool=client.app.state.redis_pool).flushdb()


def post_form(
    client: TestClient,
    path: str,
    data: dict[str, Any],
    token: str | None = None,
    params: dict[str, Any] | None = None,
):
    """POST form data with matching CSRF cookie + field."""
    client.cookies.set("csrf_token", CSRF)
    payload = {**data, "csrf_token": CSRF}
    headers = auth(token) if token else {}
    return client.post(
        path,
        data=payload,
        headers=headers,
        params=params,
        follow_redirects=False,
    )


def get(client: TestClient, path: str, token: str | None = None, **kwargs):
    headers = {**kwargs.pop("headers", {}), **(auth(token) if token else {})}
    return client.get(path, headers=headers, follow_redirects=False, **kwargs)


def delete(client: TestClient, path: str, token: str | None = None, **kwargs):
    headers = {**kwargs.pop("headers", {}), **(auth(token) if token else {})}
    return client.delete(path, headers=headers, follow_redirects=False, **kwargs)


def spreadsheet_payload(columns: list[str], rows: list[list[Any]]) -> dict[str, str]:
    """JSON-encode spreadsheet cells and display-name headers for SpreadsheetInputField."""
    return {
        "spreadsheet": json.dumps(rows),
        "columns": json.dumps(columns),
    }
