"""AddSeqRequestShareEmailAction: render, permissions, validation, and sharing.

Access control:
- **Init()** requires the seq request to exist (404 if not).
- **GET (Begin)** requires WRITE on the seq request.
- **POST (Submit)** requires WRITE on the seq request.
- Duplicate emails are rejected.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_seq_request
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

PREFIX = "/htmx/seq_requests"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"

TEST_EMAIL = "share@example.com"


def _render_path(seq_request_id: int) -> str:
    return f"{PREFIX}/{seq_request_id}/share-email"


def _submit_path(seq_request_id: int) -> str:
    return f"{PREFIX}/{seq_request_id}/share-email"


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "email": TEST_EMAIL,
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _commit(session: SyncSession) -> None:
    session.commit()


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_get_allows_owner(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """Seq request owner has WRITE access."""
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = get(client, _render_path(seq_request.id), user_token)

    assert response.status_code == 200
    assert 'name="email"' in response.text
    assert 'name="csrf_token"' in response.text


def test_render_get_denies_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    """A user with no relationship to the seq request lacks WRITE."""
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = get(client, _render_path(seq_request.id), user_2_token)

    assert response.status_code == 403


def test_render_get_unknown_is_404(
    client: TestClient,
    user_token: str,
):
    assert get(client, _render_path(999999), user_token).status_code == 404


# ── Submit (POST) ────────────────────────────────────────────────────────────


def test_submit_requires_write(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    """A stranger lacks WRITE and is denied."""
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(email=TEST_EMAIL),
        token=user_2_token,
    )

    assert response.status_code == 403


def test_submit_adds_email(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(email=TEST_EMAIL),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert_flash(response, f"Email {TEST_EMAIL} added successfully.", category="success")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert any(link.email == TEST_EMAIL for link in updated.delivery_email_links)


def test_submit_rejects_duplicate_email(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    seq_request = create_seq_request(session, user)
    seq_request.delivery_email_links.append(
        models.links.SeqRequestDeliveryEmailLink(email=TEST_EMAIL)
    )
    session.save(seq_request)
    _commit(session)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(email=TEST_EMAIL),
        token=user_token,
    )

    assert_form_invalid(response)
    assert "already in the list" in response.text


def test_submit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form_csrf_mismatch(
        client,
        _submit_path(seq_request.id),
        _payload(email=TEST_EMAIL),
        token=user_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")


def test_submit_unknown_is_404(
    client: TestClient,
    user_token: str,
):
    response = post_form(
        client,
        _submit_path(999999),
        _payload(email=TEST_EMAIL),
        token=user_token,
    )

    assert response.status_code == 404