"""ProcessSeqRequestAction: render, permissions, validation, and processing.

Access control:
- **Init()** requires the seq request to exist (404 if not).
- **GET (Begin)** requires ``require_insider`` — only staff can view.
- **POST (Submit)** requires ``require_insider``.
- Accepts / rejects / marks as pending revision a sequencing request.
"""

import re

import pytest

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from opengsync_db import actions
from opengsync_db.transitions import tracking

from ...db.create_units import create_seq_request, create_library, create_project, create_sample
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
            notification_comment="Samples degraded",
            assign_seq_request_to_me="on",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert_flash(response, "Request rejected!", category="info")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert updated.status == C.SeqRequestStatus.REJECTED



def test_submit_reject_keeps_samples_draft(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """REJECTED samples are failed in the lab and can't be re-submitted; a rejected request's samples stay DRAFT."""
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    sample = create_sample(session, user, create_project(session, user))
    sample.status = C.SampleStatus.DRAFT
    actions.link_sample_library(session, sample_id=sample.id, library_id=library.id)
    session.commit()

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(response_type=str(C.RequestResponse.REJECTED.id), notification_comment="Samples degraded"),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    session.expire_all()
    assert session.get_one(Q.sample.select(id=sample.id)).status == C.SampleStatus.DRAFT

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
            notification_comment="Please fix the organism",
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


def test_submit_with_cached_user_who_already_commented(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """Regression: the cached current_user must not clash with the same user loaded as a comment author."""
    seq_request = _seq_request_with_library(session, user)
    seq_request.comments.append(Q.comment.create(text="Earlier comment", author=insider))
    session.commit()

    # Warm the user cache so the POST resolves current_user from Redis, not the DB.
    assert get(client, _render_path(seq_request.id), insider_token).status_code == 200

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
    assert len(updated.comments) == 2
    assert all(c.author_id == insider.id for c in updated.comments)
    assert insider in updated.assignees


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


def test_submit_unchecked_assign_does_not_assign(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """An unchecked checkbox sends nothing; the field's default (on) must not apply to the submission."""
    seq_request = _seq_request_with_library(session, user)
    payload = _payload(response_type=str(C.RequestResponse.ACCEPTED.id))
    del payload["assign_seq_request_to_me"]

    response = post_form(client, _submit_path(seq_request.id), payload, token=insider_token)

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert insider not in updated.assignees


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

# ── Notification email ─────────────────────────────────────────────────────


def _submitted_by(session: SyncSession, seq_request: models.SeqRequest, actor: models.User) -> None:
    tracking.set_actor(session, actor.id)
    actions.submit_seq_request(session, seq_request)
    tracking.set_actor(session, None)
    session.commit()


def _notifications(fake_mailer) -> list[dict]:
    return [mail for mail in fake_mailer.sent if mail["method"] == "send_seq_request_processed"]


def test_render_notify_checked_when_customer_submitted(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    seq_request = _seq_request_with_library(session, user)
    _submitted_by(session, seq_request, user)

    response = get(client, _render_path(seq_request.id), insider_token)

    assert response.status_code == 200
    assert re.search(r'<input[^>]*name="notify_customer"[^>]*checked', response.text)
    assert "Submitted by the customer" in response.text


def test_render_notify_unchecked_when_insider_submitted(
    client: TestClient, session: SyncSession, user, insider, insider_token: str,
):
    """Insiders fill in and submit requests on a customer's behalf: the requestor field cannot tell."""
    seq_request = _seq_request_with_library(session, user)
    _submitted_by(session, seq_request, insider)

    response = get(client, _render_path(seq_request.id), insider_token)

    assert response.status_code == 200
    assert not re.search(r'<input[^>]*name="notify_customer"[^>]*checked', response.text)
    assert "Submitted by staff" in response.text


def test_render_notify_unchecked_without_tracked_submit(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    seq_request = _seq_request_with_library(session, user)

    response = get(client, _render_path(seq_request.id), insider_token)

    assert not re.search(r'<input[^>]*name="notify_customer"[^>]*checked', response.text)
    assert "Submitter unknown" in response.text


def test_latest_submit_decides(session: SyncSession, user, insider):
    """Resubmission after revision: the latest submitter counts."""
    seq_request = _seq_request_with_library(session, user)
    _submitted_by(session, seq_request, insider)
    actions.process_seq_request(session=session, seq_request=seq_request, status=C.SeqRequestStatus.DRAFT)
    session.commit()
    _submitted_by(session, seq_request, user)

    assert session.first(Q.seq_request.submitted_by(seq_request.id)).id == user.id


def test_submit_with_notify_sends_email(
    client: TestClient, session: SyncSession, user, insider_token: str, fake_mailer,
):
    seq_request = _seq_request_with_library(session, user)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(
            response_type=str(C.RequestResponse.PENDING_REVISION.id),
            notification_comment="Please fix the organism",
            notify_customer="on",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    [mail] = _notifications(fake_mailer)
    receiver, sent_request, response_type = mail["args"]
    assert (receiver, sent_request.id, response_type) == (
        "notify@example.com", seq_request.id, C.RequestResponse.PENDING_REVISION,
    )
    assert mail["kwargs"]["comment"] == "Please fix the organism"


def test_submit_without_notify_sends_nothing(
    client: TestClient, session: SyncSession, user, insider_token: str, fake_mailer,
):
    seq_request = _seq_request_with_library(session, user)

    response = post_form(client, _submit_path(seq_request.id), _payload(), token=insider_token)

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert _notifications(fake_mailer) == []


def test_notify_requires_receiver(
    client: TestClient, session: SyncSession, user, insider_token: str, fake_mailer,
):
    seq_request = _seq_request_with_library(session, user)
    status = seq_request.status

    response = post_form(
        client, _submit_path(seq_request.id),
        _payload(notification_receiver="", notify_customer="on"), token=insider_token,
    )

    assert_form_invalid(response, "Notification email is required to notify the customer.")
    assert _notifications(fake_mailer) == []
    session.expire_all()
    assert session.get_one(Q.seq_request.select(id=seq_request.id)).status == status


def test_reject_requires_comment(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    """Legacy parity: the customer must be told why a request was not accepted."""
    seq_request = _seq_request_with_library(session, user)

    response = post_form(
        client, _submit_path(seq_request.id),
        _payload(response_type=str(C.RequestResponse.REJECTED.id), notification_comment="  "), token=insider_token,
    )

    assert_form_invalid(response, "A comment is required if the request is not accepted.")


def test_mail_failure_still_processes_request(
    client: TestClient, session: SyncSession, user, insider_token: str, fake_mailer,
):
    seq_request = _seq_request_with_library(session, user)
    fake_mailer.fail = True

    response = post_form(
        client, _submit_path(seq_request.id), _payload(notify_customer="on"), token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert_flash(response, "notification email to notify@example.com could not be sent", category="warning")
    session.expire_all()
    assert session.get_one(Q.seq_request.select(id=seq_request.id)).status == C.SeqRequestStatus.ACCEPTED


@pytest.mark.parametrize("response_type, wording", [
    (C.RequestResponse.ACCEPTED, "has been accepted"),
    (C.RequestResponse.REJECTED, "has been rejected"),
    (C.RequestResponse.PENDING_REVISION, "needs revision"),
])
def test_notification_email_renders(
    client: TestClient, session: SyncSession, user, monkeypatch: pytest.MonkeyPatch, response_type, wording: str,
):
    """The real template: wording per response, escaped comment, contact greeting, request link."""
    from server.core import mailer as mailer_module

    sent: list[dict] = []
    monkeypatch.setattr(mailer_module.responses, "external_url_for", lambda *args, **kwargs: "https://example.com/seq_requests/1")
    monkeypatch.setattr(mailer_module.templates.context, "get_request_context", lambda: {})
    monkeypatch.setattr(mailer_module.Mailer, "_get_email_style", lambda self: "")
    monkeypatch.setattr(mailer_module.Mailer, "_Mailer__send_email", lambda _, **kwargs: sent.append(kwargs))
    seq_request = _seq_request_with_library(session, user)

    mailer_module.Mailer().send_seq_request_processed(
        seq_request.contact_person.email, seq_request, response_type, comment="<b>fix</b> the organism",
    )

    [mail] = sent
    assert mail["recipients"] == seq_request.contact_person.email
    assert mail["subject"].startswith(f"[R{seq_request.id}] Sequencing Request {response_type.display_name}")
    assert wording in mail["body"]
    assert f"Dear {seq_request.contact_person.name}" in mail["body"]
    assert "&lt;b&gt;fix&lt;/b&gt; the organism" in mail["body"]
    assert "https://example.com/seq_requests/1" in mail["body"]
