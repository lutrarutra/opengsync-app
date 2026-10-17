"""SelectPoolLibrariesAction: render, permissions, and adding libraries to a pool.

Access control:
- **Init()** requires the pool to exist (404 if not).
- **GET (Begin)** requires ``require_insider`` — only staff can view.
- **POST (Submit)** requires ``require_insider``.
- ``selected_library_ids`` is not required, so an empty selection passes validation.
"""

import json

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_pool, create_seq_request, create_library
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

PREFIX = "/htmx/actions/select-pool-libraries"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _render_path(pool_id: int) -> str:
    return f"{PREFIX}/{pool_id}"


def _submit_path(pool_id: int) -> str:
    return f"{PREFIX}/{pool_id}"


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "selected_library_ids": json.dumps([]),
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _commit(session: SyncSession) -> None:
    session.commit()


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_get_allows_insider(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    response = get(client, _render_path(pool.id), insider_token)

    assert response.status_code == 200
    assert 'name="selected_library_ids"' in response.text
    assert 'name="csrf_token"' in response.text


def test_render_get_denies_client(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """A CLIENT user lacks insider access and is denied."""
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    response = get(client, _render_path(pool.id), user_token)

    assert response.status_code == 403


def test_render_get_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    assert get(client, _render_path(999999), insider_token).status_code == 404


# ── Submit (POST) ────────────────────────────────────────────────────────────


def test_submit_requires_insider(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """A CLIENT user lacks insider access and is denied."""
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    response = post_form(
        client,
        _submit_path(pool.id),
        _payload(),
        token=user_token,
    )

    assert response.status_code == 403


def test_submit_adds_libraries_to_pool(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    library = create_library(session, user, seq_request)
    assert library.pool_id is None
    _commit(session)

    response = post_form(
        client,
        _submit_path(pool.id),
        _payload(selected_library_ids=json.dumps([library.id])),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/pools/{pool.id}")
    assert_flash(response, "Libraries added to pool!", category="success")

    session.expire_all()
    updated = session.get_one(Q.library.select(id=library.id))
    assert updated.pool_id == pool.id


def test_submit_empty_selection(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """An empty library selection is valid (field not required) and redirects."""
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    response = post_form(
        client,
        _submit_path(pool.id),
        _payload(selected_library_ids=json.dumps([])),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/pools/{pool.id}")
    assert_flash(response, "Libraries added to pool!", category="success")


def test_submit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    response = post_form_csrf_mismatch(
        client,
        _submit_path(pool.id),
        _payload(),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")


def test_submit_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    response = post_form(
        client,
        _submit_path(999999),
        _payload(),
        token=insider_token,
    )

    assert response.status_code == 404