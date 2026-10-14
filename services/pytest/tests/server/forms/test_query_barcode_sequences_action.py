"""QueryBarcodeSequencesAction: render and search barcode sequences.

Access control:
- The routes themselves have **no auth gate**, but the app's global auth
  middleware requires a valid session, so all tests pass a user token.
- GET renders the search form with a sequence input field.
- POST takes ``sequence`` as a **form field** (the search input posts via
  ``hx-include``), searches barcode sequences in the DB, and returns
  ``components/barcode_results.html`` with forward and reverse-complement hits.
"""

import uuid

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from .._http import (
    get,
    post_form,
    post_form_csrf_mismatch,
)

PREFIX = "/htmx/kits"


def _path() -> str:
    return f"{PREFIX}/query-barcode-sequences"


def _kit_with_barcode(session: SyncSession, sequence: str) -> models.IndexKit:
    _uuid = str(uuid.uuid1())
    kit = session.save(Q.index_kit.create(
        name=_uuid, identifier=_uuid[:12], type=C.IndexType.SINGLE_INDEX_I7, supported_protocol_ids=[],
    ), flush=True)
    adapter = session.save(Q.adapter.create(index_kit=kit, well="A1"), flush=True)
    session.save(Q.barcode.create(
        name="QUERY_I7_A1", sequence=sequence, well="A1", type=C.BarcodeType.INDEX_I7, adapter=adapter,
    ), flush=True)
    session.commit()
    return kit


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


def test_search_renders_matching_barcode(
    client: TestClient,
    session: SyncSession,
    user_token: str,
):
    """A matching sequence posted in the form body is rendered in the forward results."""
    kit = _kit_with_barcode(session, "ACGTACGTAA")

    response = post_form(client, _path(), data={"sequence": "acgtacgtaa"}, token=user_token)

    assert response.status_code == 200
    assert "Forward" in response.text
    assert "Reverse Complement" in response.text
    assert "ACGTACGTAA" in response.text
    assert "QUERY_I7_A1" in response.text
    assert f"/index-kits/{kit.id}" in response.text


def test_search_matches_reverse_complement(
    client: TestClient,
    session: SyncSession,
    user_token: str,
):
    """Searching the reverse complement of a stored barcode still finds it."""
    _kit_with_barcode(session, "AAAACCCCGG")

    response = post_form(client, _path(), data={"sequence": "CCGGGGTTTT"}, token=user_token)

    assert response.status_code == 200
    assert "AAAACCCCGG" in response.text


def test_search_returns_empty_for_no_match(
    client: TestClient,
    session: SyncSession,
    user_token: str,
):
    """POST with a sequence that does not match returns 200."""
    response = post_form(client, _path(), data={"sequence": "ACGT"}, token=user_token)

    assert response.status_code == 200
    assert "Forward" in response.text


def test_search_handles_empty_sequence(
    client: TestClient,
    session: SyncSession,
    user_token: str,
):
    """POST with an empty sequence returns the empty results component, not a validation error."""
    response = post_form(client, _path(), data={"sequence": ""}, token=user_token)

    assert response.status_code == 200
    assert "Forward" in response.text
    assert "Reverse Complement" in response.text
    assert "is required" not in response.text


def test_search_csrf_mismatch_is_rejected(
    client: TestClient,
    session: SyncSession,
    user_token: str,
):
    """Validate() rejects a CSRF mismatch before any search runs."""
    _kit_with_barcode(session, "ACGTACGTCC")

    response = post_form_csrf_mismatch(
        client,
        _path(),
        data={"sequence": "ACGTACGTCC"},
        token=user_token,
    )

    assert response.status_code != 200
    assert "ACGTACGTCC" not in response.text
