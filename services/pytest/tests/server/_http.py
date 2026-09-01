import json
import re
from html import unescape
from typing import Any
from urllib.parse import unquote

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


def htmx_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"HX-Request": "true"}
    if extra:
        headers.update(extra)
    return headers


def flush_redis(client: OpenGSyncTestClient) -> None:
    from redis import Redis
    Redis(connection_pool=client.app.state.redis_pool).flushdb()


def _request_headers(
    token: str | None = None,
    htmx: bool = False,
    headers: dict[str, str] | None = None,
) -> dict[str, str]:
    req_headers: dict[str, str] = {}
    if token:
        req_headers.update(auth(token))
    if htmx:
        req_headers.update(htmx_headers())
    if headers:
        req_headers.update(headers)
    return req_headers


def post_form(
    client: TestClient,
    path: str,
    data: dict[str, Any],
    token: str | None = None,
    params: dict[str, Any] | None = None,
    htmx: bool = False,
    headers: dict[str, str] | None = None,
):
    """POST form data with matching CSRF cookie + field."""
    client.cookies.set("csrf_token", CSRF)
    payload = {**data, "csrf_token": CSRF}
    return client.post(
        path,
        data=payload,
        headers=_request_headers(token=token, htmx=htmx, headers=headers),
        params=params,
        follow_redirects=False,
    )


def post_form_csrf_mismatch(
    client: TestClient,
    path: str,
    data: dict[str, Any],
    token: str | None = None,
    params: dict[str, Any] | None = None,
    cookie: str = "cookie-token",
    field: str = "body-token",
    htmx: bool = False,
    headers: dict[str, str] | None = None,
):
    """POST form data with a CSRF cookie that does not match the field."""
    client.cookies.set("csrf_token", cookie)
    payload = {**data, "csrf_token": field}
    return client.post(
        path,
        data=payload,
        headers=_request_headers(token=token, htmx=htmx, headers=headers),
        params=params,
        follow_redirects=False,
    )


def put_form(
    client: TestClient,
    path: str,
    data: dict[str, Any],
    token: str | None = None,
    params: dict[str, Any] | None = None,
    htmx: bool = False,
    headers: dict[str, str] | None = None,
):
    """PUT form data with matching CSRF cookie + field."""
    client.cookies.set("csrf_token", CSRF)
    payload = {**data, "csrf_token": CSRF}
    return client.put(
        path,
        data=payload,
        headers=_request_headers(token=token, htmx=htmx, headers=headers),
        params=params,
        follow_redirects=False,
    )


def get(
    client: TestClient,
    path: str,
    token: str | None = None,
    htmx: bool = False,
    **kwargs,
):
    extra_headers = kwargs.pop("headers", {})
    headers = _request_headers(token=token, htmx=htmx, headers=extra_headers)
    return client.get(path, headers=headers, follow_redirects=False, **kwargs)


def delete(client: TestClient, path: str, token: str | None = None, htmx: bool = False, **kwargs):
    extra_headers = kwargs.pop("headers", {})
    headers = _request_headers(token=token, htmx=htmx, headers=extra_headers)
    return client.delete(path, headers=headers, follow_redirects=False, **kwargs)


def spreadsheet_payload(columns: list[str], rows: list[list[Any]]) -> dict[str, str]:
    """JSON-encode spreadsheet cells and display-name headers for SpreadsheetInputField."""
    return {
        "spreadsheet": json.dumps(rows),
        "columns": json.dumps(columns),
    }


def set_cookie_header(response) -> str:
    headers = response.headers
    if hasattr(headers, "get_list"):
        return "\n".join(headers.get_list("set-cookie"))
    if hasattr(headers, "getlist"):
        return "\n".join(headers.getlist("set-cookie"))
    return headers.get("set-cookie", "") or ""


def assert_form_invalid(response, contains: str | None = None) -> None:
    """Validation failures re-render the form with HTTP 202."""
    assert response.status_code == 202
    if contains is not None:
        assert contains in unescape(response.text)


def assert_htmx_redirect(response, contains: str = "/") -> None:
    assert response.status_code == 204
    location = response.headers.get("HX-Redirect", "")
    assert contains in location, f"HX-Redirect {location!r} does not contain {contains!r}"


def assert_cookie_set(response, name: str) -> None:
    header = set_cookie_header(response)
    assert name in response.cookies or f"{name}=" in header, f"{name} cookie was not set"


def assert_flash(response, message: str, category: str | None = None) -> None:
    """Flash may be an HX-Trigger event (inline) or a flash_message cookie (redirect)."""
    trigger = response.headers.get("HX-Trigger", "")
    cookies = unquote(set_cookie_header(response))
    haystack = f"{unquote(trigger)}\n{cookies}"
    assert message in haystack, f"flash {message!r} not found in {haystack!r}"
    if category is not None:
        assert category in haystack


def flash_cookie_payload(response) -> dict[str, Any] | None:
    match = re.search(r"flash_message=([^;]+)", set_cookie_header(response))
    if match is None:
        return None
    return json.loads(unquote(match.group(1)))
