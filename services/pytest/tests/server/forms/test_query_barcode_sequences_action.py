"""QueryBarcodeSequencesAction: render and search barcode sequences.

Access control:
- The routes themselves have **no auth gate**, but the app's global auth
  middleware requires a valid session, so all tests pass a user token.
- GET renders the search form with a sequence input field.
- POST takes ``sequence`` as a **query parameter**, searches barcode
  sequences in the DB, and returns ``components/barcode_results.html``.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession

from .._http import (
    get,
    post_form,
    post_form_csrf_mismatch,
)

PREFIX = "/htmx/kits"


def _path() -> str:
    return f"{PREFIX}/query-barcode-sequences"


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_get_shows_form(
    client: TestClient,
    user_token: str,
):
    """Any authenticated user can view the barcode query form."""
    response = get(client, _path(), user_token)

    assert response.status_code == 200
    assert 'name="sequence"' in response.text
    assert 'name="csrf_token"' in response.text
    assert "Query Barcode Sequences" in response.text


# ── Search (POST) ───────────────────────────────────────────────────────────


def test_search_returns_empty_for_no_match(
    client: TestClient,
    session: SyncSession,
    user_token: str,
):
    """POST with a sequence that does not match returns 200."""
    response = post_form(
        client,
        _path(),
        data={},
        params={"sequence": "ACGT"},
        token=user_token,
    )

    assert response.status_code == 200


def test_search_handles_empty_sequence(
    client: TestClient,
    session: SyncSession,
    user_token: str,
):
    """POST with an empty sequence returns 200."""
    response = post_form(
        client,
        _path(),
        data={},
        params={"sequence": ""},
        token=user_token,
    )

    assert response.status_code == 200


def test_search_csrf_mismatch_still_succeeds(
    client: TestClient,
    session: SyncSession,
    user_token: str,
):
    """The Search route does not call Validate() — CSRF is not checked."""
    response = post_form_csrf_mismatch(
        client,
        _path(),
        data={},
        params={"sequence": "ACGT"},
        token=user_token,
    )

    assert response.status_code == 200