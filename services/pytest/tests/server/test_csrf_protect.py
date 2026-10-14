"""Central CSRF check (``dependencies.csrf_protect``) for state-changing requests.

Every POST/PUT/PATCH/DELETE made with the login cookie must send the ``csrf_token`` cookie back,
as the ``X-CSRF-Token`` header (htmx adds it to every request, see base.html) or as the
``csrf_token`` form field. HTMXForm routes check the token themselves (and re-render the form
with a flash), as do chat and passkeys (``verify_csrf_header``). Requests without the login
cookie (anonymous, ``X-API-Token``) carry no ambient credentials and are not checked.

Legacy had no global CSRF protection (only per-form WTForms tokens).
"""

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q

from ..db.create_units import create_pool, create_seq_request
from ._http import CSRF, cookie_header, get

TOKEN_INVALID = "Security token invalid or missing"


def _request(client: TestClient, method: str, path: str, token: str | None, *, header: str | None = None, cookie: str | None = CSRF, form: dict | None = None):
    cookies = {"csrf_token": cookie} if cookie is not None else {}
    headers = cookie_header(client, token, **cookies)
    if header is not None:
        headers["X-CSRF-Token"] = header
    return client.request(method, path, headers=headers, data=form, follow_redirects=False)


@pytest.fixture
def pool(session: SyncSession, user):
    pool = create_pool(session, user, create_seq_request(session, user))
    session.commit()
    return pool


def _pool_exists(session: SyncSession, pool_id: int) -> bool:
    session.expire_all()
    return session.first(Q.pool.select(id=pool_id)) is not None


# ── Plain (non-form) routes ─────────────────────────────────────────────────


@pytest.mark.parametrize("header, cookie", [
    (None, CSRF),          # no token sent
    ("other", CSRF),       # token does not match the cookie
    (CSRF, None),          # no cookie to compare with
    ("", CSRF),            # empty header
], ids=["missing", "mismatch", "no-cookie", "empty"])
def test_plain_route_without_valid_token_is_rejected(
    client: TestClient, session: SyncSession, pool, insider_token: str, header, cookie,
):
    pool_id = pool.id
    response = _request(client, "DELETE", f"/htmx/pools/{pool_id}/delete", insider_token, header=header, cookie=cookie)

    assert response.status_code == 403
    assert TOKEN_INVALID in response.text
    assert _pool_exists(session, pool_id)


def test_plain_route_with_token_header_succeeds(client: TestClient, session: SyncSession, pool, insider_token: str):
    pool_id = pool.id
    response = _request(client, "DELETE", f"/htmx/pools/{pool_id}/delete", insider_token, header=CSRF)

    assert response.status_code == 204, response.text
    assert not _pool_exists(session, pool_id)


def test_plain_route_accepts_the_token_as_form_field(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = create_seq_request(session, user)
    session.commit()

    response = _request(client, "POST", f"/htmx/seq_requests/{seq_request.id}/clone?method=raw", user_token, form={"csrf_token": CSRF})

    assert response.status_code == 204, response.text


@pytest.mark.parametrize("method, path", [
    ("POST", "/htmx/auth/logout"),
    ("POST", "/htmx/seq_requests/{seq_request_id}/clone?method=raw"),
    ("POST", "/htmx/seq_requests/{seq_request_id}/archive"),
    ("DELETE", "/htmx/seq_requests/{seq_request_id}/delete"),
])
def test_other_plain_routes_are_covered(client: TestClient, session: SyncSession, user, user_token: str, method: str, path: str):
    seq_request = create_seq_request(session, user)
    session.commit()

    response = _request(client, method, path.format(seq_request_id=seq_request.id), user_token)

    assert response.status_code == 403
    assert TOKEN_INVALID in response.text


def test_api_route_with_login_cookie_needs_the_token(client: TestClient, insider_token: str):
    headers = cookie_header(client, insider_token, csrf_token=CSRF)
    response = client.post("/api/projects/add-software", json={}, headers=headers)

    assert response.status_code == 403
    assert TOKEN_INVALID in response.text


# ── Not checked here ────────────────────────────────────────────────────────


def test_get_is_not_checked(client: TestClient, insider_token: str):
    assert get(client, "/htmx/pools/create", insider_token).status_code == 200


def test_anonymous_request_is_not_checked(client: TestClient, pool):
    """No login cookie, so no CSRF risk: the request is redirected to the login page instead."""
    response = _request(client, "DELETE", f"/htmx/pools/{pool.id}/delete", None, cookie=None)

    assert response.status_code == 303


def test_api_token_request_is_not_checked(client: TestClient, session: SyncSession, insider):
    """API clients authenticate with X-API-Token (no cookie), so they need no CSRF token."""
    api_token = session.save(Q.api_token.create(owner=insider, time_valid_min=60), flush=True)
    plaintext = api_token.plaintext
    session.commit()

    response = client.post("/api/projects/add-software", json={}, headers={"X-API-Token": plaintext})

    assert response.status_code != 403
    assert TOKEN_INVALID not in response.text


def test_forms_keep_their_own_check_and_rerender(client: TestClient, insider_token: str):
    """A form route is skipped by the central check: a bad token re-renders the form (202) with a flash."""
    headers = cookie_header(client, insider_token, csrf_token="cookie-token")
    response = client.post("/htmx/pools/create", data={"csrf_token": "field-token", "name": "x"}, headers=headers, follow_redirects=False)

    assert response.status_code == 202


def test_base_page_sends_the_token_with_htmx(client: TestClient, user_token: str):
    page = get(client, "/", user_token)

    assert page.status_code == 200
    assert 'htmx:configRequest' in page.text
    assert 'X-CSRF-Token' in page.text


# ── Route table ─────────────────────────────────────────────────────────────


def _routes(routes, prefix=""):
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            yield from _routes(route.original_router.routes, prefix + (route.include_context.prefix or ""))
        elif isinstance(route, APIRoute):
            yield prefix, route


def test_every_state_changing_route_is_behind_the_check(client: TestClient):
    """All app routes are included with ``csrf_protect`` (main.py); a router added without it fails here."""
    from server.core import dependencies

    unprotected = []
    for top in client.app.routes:
        if type(top).__name__ != "_IncludedRouter":
            continue
        protected = any(dep.dependency is dependencies.csrf_protect for dep in top.include_context.dependencies)
        for prefix, route in _routes([top]):
            if route.methods & {"POST", "PUT", "PATCH", "DELETE"} and not protected:
                unprotected.append(f"{sorted(route.methods)} {prefix}{route.path}")

    assert unprotected == []
