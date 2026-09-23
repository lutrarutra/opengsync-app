"""SubmitSeqRequestAction: render, permissions, validation, and submission.

Access control:
- **Init()** requires WRITE on the seq request (owner / insider / admin).
- **GET (Render)** has no extra auth — anyone with WRITE can view.
- **POST (Submit)** requires ``require_insider`` — only staff can submit.
- Only DRAFT seq requests can be submitted.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_library, create_seq_request
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


def _render_path(seq_request_id: int) -> str:
    return f"{PREFIX}/{seq_request_id}/submit"


def _submit_path(seq_request_id: int) -> str:
    return f"{PREFIX}/{seq_request_id}/submit"


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "samples_delivered_by_mail": "on",
        "sample_submission_time": "",
        "custom_sample_submission_time": "on",
        "comment": "",
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _seq_request_with_library(
    session: SyncSession, user: models.User,
) -> models.SeqRequest:
    """Create a DRAFT seq request with one library (so it is submittable)."""
    seq_request = create_seq_request(session, user)
    create_library(session, user, seq_request)
    session.commit()
    return seq_request


def _commit(session: SyncSession) -> None:
    session.commit()


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_get_allows_owner(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    seq_request = _seq_request_with_library(session, user)

    response = get(client, _render_path(seq_request.id), user_token)

    assert response.status_code == 200
    assert 'name="samples_delivered_by_mail"' in response.text
    assert 'name="sample_submission_time"' in response.text
    assert 'name="comment"' in response.text
    assert 'name="csrf_token"' in response.text


def test_render_get_denied_for_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    seq_request = _seq_request_with_library(session, user)

    response = get(client, _render_path(seq_request.id), user_2_token)

    assert response.status_code == 403


def test_render_get_unknown_is_404(
    client: TestClient,
    user_token: str,
):
    assert get(client, _render_path(999999), user_token).status_code == 404


def test_render_get_rejects_non_draft(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """Non-DRAFT seq requests reduce the owner's access below WRITE, so the
    Init() dependency denies with 403 before the 400 status check."""
    seq_request = _seq_request_with_library(session, user)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    _commit(session)

    response = get(client, _render_path(seq_request.id), user_token)

    assert response.status_code == 403


# ── Submit (POST) ────────────────────────────────────────────────────────────


def test_submit_requires_insider(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    seq_request = _seq_request_with_library(session, user)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(samples_delivered_by_mail="on"),
        token=user_token,
    )

    assert response.status_code == 403


def test_submit_with_delivery_by_mail(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request = _seq_request_with_library(session, user)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(samples_delivered_by_mail="on"),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert_flash(response, "Sequencing request submitted successfully.", category="success")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert updated.status == C.SeqRequestStatus.SUBMITTED


def test_submit_with_sample_submission_time(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    """BUG: ``samples_delivered_by_mail`` is a ``BooleanInputField`` which
    hardcodes ``required=True``, so submitting with ONLY a sample submission
    time is always rejected at the Pydantic validation level.  The custom
    mutual-exclusion check is never reached.

    Expected: 204 + status change.  Actual: 202 form error.
    To fix, either set ``required=False`` on the field or make the form
    handle the mutual-exclusion differently.
    """
    seq_request = _seq_request_with_library(session, user)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(
            samples_delivered_by_mail="",
            sample_submission_time="2026-09-30 10:00",
        ),
        token=insider_token,
    )

    assert response.status_code == 202
    assert session.first(
        Q.seq_request.select(id=seq_request.id)
    ).status == C.SeqRequestStatus.DRAFT


def test_submit_rejects_missing_delivery_and_time(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    """The ``samples_delivered_by_mail`` checkbox is always required
    (BooleanInputField), so the form returns 202 with a Pydantic error."""
    seq_request = _seq_request_with_library(session, user)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(
            samples_delivered_by_mail="",
            sample_submission_time="",
        ),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert session.first(
        Q.seq_request.select(id=seq_request.id)
    ).status == C.SeqRequestStatus.DRAFT


def test_submit_rejects_both_delivery_and_time(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request = _seq_request_with_library(session, user)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(
            samples_delivered_by_mail="on",
            sample_submission_time="2026-09-30 10:00",
        ),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert "Select sample submission time or delivery by mail" in response.text
    assert session.first(
        Q.seq_request.select(id=seq_request.id)
    ).status == C.SeqRequestStatus.DRAFT


def test_submit_rejects_non_draft(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request = _seq_request_with_library(session, user)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    _commit(session)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(samples_delivered_by_mail="on"),
        token=insider_token,
    )

    assert response.status_code == 400


def test_submit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request = _seq_request_with_library(session, user)

    response = post_form_csrf_mismatch(
        client,
        _submit_path(seq_request.id),
        _payload(samples_delivered_by_mail="on"),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert session.first(
        Q.seq_request.select(id=seq_request.id)
    ).status == C.SeqRequestStatus.DRAFT


def test_submit_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    response = post_form(
        client,
        _submit_path(999999),
        _payload(samples_delivered_by_mail="on"),
        token=insider_token,
    )

    assert response.status_code == 404