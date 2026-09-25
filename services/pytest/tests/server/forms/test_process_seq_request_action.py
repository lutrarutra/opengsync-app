"""ProcessSeqRequestAction: render, permissions, validation, and processing.

Access control:
- **Init()** requires the seq request to exist (404 if not).
- **GET (Begin)** requires ``require_insider`` — only staff can view.
- **POST (Submit)** requires ``require_insider``.
- Accepts / rejects / marks as pending revision a sequencing request.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_seq_request, create_library
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
    return f"{PREFIX}/{seq_request_id}/process-request"


def _submit_path(seq_request_id: int) -> str:
    return f"{PREFIX}/{seq_request_id}/process-request"


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "response_type": str(C.RequestResponse.ACCEPTED.id),
        "notification_receiver": "notify@example.com",
        "notification_comment": "",
        "assign_seq_request_to_me": "on",
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _seq_request_with_library(
    session: SyncSession, user: models.User,
) -> models.SeqRequest:
    seq_request = create_seq_request(session, user)
    create_library(session, user, seq_request)
    session.commit()
    return seq_request


def _commit(session: SyncSession) -> None:
    session.commit()


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_get_allows_insider(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request = _seq_request_with_library(session, user)

    response = get(client, _render_path(seq_request.id), insider_token)

    assert response.status_code == 200
    assert 'name="response_type"' in response.text
    assert 'name="notification_receiver"' in response.text
    assert 'name="notification_comment"' in response.text
    assert 'name="assign_seq_request_to_me"' in response.text
    assert 'name="csrf_token"' in response.text


def test_render_get_denies_client(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    seq_request = _seq_request_with_library(session, user)

    response = get(client, _render_path(seq_request.id), user_token)

    assert response.status_code == 403


def test_render_get_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    assert get(client, _render_path(999999), insider_token).status_code == 404


def test_render_get_prefills_contact_email(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    """The notification_receiver field is pre-filled with the contact email."""
    seq_request = _seq_request_with_library(session, user)

    response = get(client, _render_path(seq_request.id), insider_token)

    assert response.status_code == 200
    assert user.email in response.text


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
        _payload(),
        token=user_token,
    )

    assert response.status_code == 403


def test_submit_accepts_request(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    seq_request = _seq_request_with_library(session, user)
    assert seq_request.status == C.SeqRequestStatus.DRAFT

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(
            response_type=str(C.RequestResponse.ACCEPTED.id),
            assign_seq_request_to_me="on",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert_flash(response, "Request accepted!", category="success")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert updated.status == C.SeqRequestStatus.ACCEPTED


def test_submit_rejects_request(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    seq_request = _seq_request_with_library(session, user)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(
            response_type=str(C.RequestResponse.REJECTED.id),
            assign_seq_request_to_me="on",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert_flash(response, "Request rejected!", category="info")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert updated.status == C.SeqRequestStatus.REJECTED


def test_submit_marks_pending_revision(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    seq_request = _seq_request_with_library(session, user)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(
            response_type=str(C.RequestResponse.PENDING_REVISION.id),
            assign_seq_request_to_me="on",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert_flash(response, "Request marked as pending revision.", category="info")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert updated.status == C.SeqRequestStatus.DRAFT


def test_submit_with_comment(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """A comment should be added to the seq request."""
    seq_request = _seq_request_with_library(session, user)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(
            response_type=str(C.RequestResponse.ACCEPTED.id),
            notification_comment="Looks good!",
            assign_seq_request_to_me="on",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert any("Looks good!" in c.text for c in updated.comments)


def test_submit_assigns_to_current_user(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """When assign_seq_request_to_me is on, the current insider is added as assignee."""
    seq_request = _seq_request_with_library(session, user)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(
            response_type=str(C.RequestResponse.ACCEPTED.id),
            assign_seq_request_to_me="on",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert insider in updated.assignees


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