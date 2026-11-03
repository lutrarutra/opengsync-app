"""AddSeqRequestShareEmailAction: the inline share-email list on the Share tab and both checklists.

Access control:
- **Init()** requires the seq request to exist (404 if not) and READ on it.
- ``context=review`` (insider review checklist) requires INSIDER for every route.
- **GET (Begin)** renders the list.
- **POST (Submit)** requires READ, so emails can be added at any status.
- **DELETE (Remove)** requires WRITE (owners only while DRAFT) and keeps at least one email.
- Adding or removing re-renders the list inline and fires ``shareEmailsChanged`` so the other
  copies on the page refresh; duplicate emails are rejected.
"""

import json

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_seq_request
from .._http import (
    assert_flash,
    assert_form_invalid,
    delete,
    get,
    post_form,
    post_form_csrf_mismatch,
)

PREFIX = "/htmx/seq_requests"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"

TEST_EMAIL = "share@example.com"
OTHER_EMAIL = "other@example.com"


def _path(seq_request_id: int, context: str = "share") -> str:
    return f"{PREFIX}/{seq_request_id}/share-email?context={context}"


def _remove_path(seq_request_id: int, email: str, context: str = "share") -> str:
    return f"{PREFIX}/{seq_request_id}/share-email/{email}?context={context}"


def _seq_request(session: SyncSession, user, *emails: str, status: C.SeqRequestStatus = C.SeqRequestStatus.DRAFT) -> models.SeqRequest:
    seq_request = create_seq_request(session, user)
    seq_request.status = status
    for email in emails:
        seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(email=email))
    session.save(seq_request)
    session.commit()
    return seq_request


def _emails(session: SyncSession, seq_request_id: int) -> list[str]:
    session.expire_all()
    return [link.email for link in session.get_one(Q.seq_request.select(id=seq_request_id)).delivery_email_links]


def _trigger(response) -> dict:
    return json.loads(response.headers["HX-Trigger"])


# ── Render (GET) ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("context", ["share", "submit"])  # type: ignore[attr-defined]
def test_render_owner(client: TestClient, session: SyncSession, user, user_token: str, context: str):
    seq_request = _seq_request(session, user, TEST_EMAIL)

    response = get(client, _path(seq_request.id, context), user_token, htmx=True)

    assert response.status_code == 200
    assert f'id="seq_request-share-emails-{context}"' in response.text
    assert TEST_EMAIL in response.text
    assert 'name="email"' in response.text
    assert 'name="csrf_token"' in response.text
    # GETs don't update the tab badge or checklist icon
    assert "hx-swap-oob" not in response.text


def test_render_empty_list(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user)

    response = get(client, _path(seq_request.id), user_token, htmx=True)

    assert response.status_code == 200
    assert "No recipients yet" in response.text


def test_render_review_context_denies_owner(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL, status=C.SeqRequestStatus.SUBMITTED)

    assert get(client, _path(seq_request.id, "review"), user_token, htmx=True).status_code == 403


def test_render_review_context_allows_insider(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL, status=C.SeqRequestStatus.SUBMITTED)

    response = get(client, _path(seq_request.id, "review"), insider_token, htmx=True)

    assert response.status_code == 200
    assert 'id="seq_request-share-emails-review"' in response.text


def test_render_unknown_context_is_rejected(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL)

    assert get(client, _path(seq_request.id, "bogus"), user_token, htmx=True).status_code == 422


def test_render_denies_stranger(client: TestClient, session: SyncSession, user, user_2_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL)

    assert get(client, _path(seq_request.id), user_2_token, htmx=True).status_code == 403


def test_render_unknown_is_404(client: TestClient, user_token: str):
    assert get(client, _path(999999), user_token, htmx=True).status_code == 404


# ── Remove button state ─────────────────────────────────────────────────────


def _remove_disabled(html: str, email: str) -> bool:
    """Whether the Remove button of ``email`` is rendered disabled."""
    button = html[:html.index(f"/share-email/{email}")]
    button = button[button.rindex("<button"):]
    return " disabled" in button


def _add_disabled(html: str) -> bool:
    button = html[html.index('<button type="submit"'):]
    return " disabled" in button[:button.index(">")]


def test_remove_enabled_for_owner_on_draft(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL, OTHER_EMAIL)

    html = get(client, _path(seq_request.id), user_token, htmx=True).text

    assert not _remove_disabled(html, TEST_EMAIL)


def test_remove_disabled_for_last_email(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL)

    html = get(client, _path(seq_request.id), insider_token, htmx=True).text

    assert _remove_disabled(html, TEST_EMAIL)
    assert "At least one email is required" in html


def test_remove_disabled_for_owner_after_submission(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL, OTHER_EMAIL, status=C.SeqRequestStatus.SUBMITTED)

    html = get(client, _path(seq_request.id), user_token, htmx=True).text

    assert _remove_disabled(html, TEST_EMAIL)
    assert "Only insiders can remove emails from a submitted request." in html
    assert not _add_disabled(html), "adding stays possible after submission"


def test_remove_enabled_for_insider_after_submission(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL, OTHER_EMAIL, status=C.SeqRequestStatus.SUBMITTED)

    html = get(client, _path(seq_request.id, "review"), insider_token, htmx=True).text

    assert not _remove_disabled(html, TEST_EMAIL)


# ── Submit (POST) ────────────────────────────────────────────────────────────


def test_submit_adds_email_inline(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user)

    response = post_form(client, _path(seq_request.id, "submit"), {"email": TEST_EMAIL}, token=user_token, htmx=True)

    assert response.status_code == 200
    assert 'id="seq_request-share-emails-submit"' in response.text
    assert TEST_EMAIL in response.text
    assert_flash(response, f"Email {TEST_EMAIL} added successfully.", category="success")
    assert _trigger(response)["shareEmailsChanged"] == {"context": "submit"}
    # the Share tab badge and the submit step icon are updated out of band
    assert 'id="request-share-tab-count" hx-swap-oob="true"' in response.text
    assert 'id="request-submit-share-emails-icon" hx-swap-oob="true">✅' in response.text
    assert _emails(session, seq_request.id) == [TEST_EMAIL]


def test_submit_strips_whitespace(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user)

    post_form(client, _path(seq_request.id), {"email": f"  {TEST_EMAIL} "}, token=user_token, htmx=True)

    assert _emails(session, seq_request.id) == [TEST_EMAIL]


def test_owner_can_add_email_to_finished_request(client: TestClient, session: SyncSession, user, user_token: str):
    """Emails can be added at any point, not only while the request is a draft."""
    seq_request = _seq_request(session, user, OTHER_EMAIL, status=C.SeqRequestStatus.FINISHED)

    response = post_form(client, _path(seq_request.id), {"email": TEST_EMAIL}, token=user_token, htmx=True)

    assert response.status_code == 200
    assert TEST_EMAIL in _emails(session, seq_request.id)


def test_insider_adds_in_review_context(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _seq_request(session, user, OTHER_EMAIL, status=C.SeqRequestStatus.SUBMITTED)

    response = post_form(client, _path(seq_request.id, "review"), {"email": TEST_EMAIL}, token=insider_token, htmx=True)

    assert response.status_code == 200
    assert _trigger(response)["shareEmailsChanged"] == {"context": "review"}
    assert TEST_EMAIL in _emails(session, seq_request.id)


def test_submit_review_context_denies_owner(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user, OTHER_EMAIL, status=C.SeqRequestStatus.SUBMITTED)

    response = post_form(client, _path(seq_request.id, "review"), {"email": TEST_EMAIL}, token=user_token, htmx=True)

    assert response.status_code == 403
    assert _emails(session, seq_request.id) == [OTHER_EMAIL]


def test_submit_denies_stranger(client: TestClient, session: SyncSession, user, user_2_token: str):
    seq_request = _seq_request(session, user)

    response = post_form(client, _path(seq_request.id), {"email": TEST_EMAIL}, token=user_2_token, htmx=True)

    assert response.status_code == 403
    assert _emails(session, seq_request.id) == []


def test_submit_rejects_duplicate_email(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL)

    response = post_form(client, _path(seq_request.id), {"email": TEST_EMAIL}, token=user_token, htmx=True)

    assert_form_invalid(response, "already in the list")
    assert 'id="seq_request-share-emails-share"' in response.text
    assert _emails(session, seq_request.id) == [TEST_EMAIL]


def test_submit_rejects_invalid_email(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user)

    response = post_form(client, _path(seq_request.id), {"email": "not-an-email"}, token=user_token, htmx=True)

    assert_form_invalid(response)
    assert "is-invalid" in response.text
    assert _emails(session, seq_request.id) == []


def test_submit_csrf_mismatch_rerenders(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user)

    response = post_form_csrf_mismatch(client, _path(seq_request.id), {"email": TEST_EMAIL}, token=user_token)

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert _emails(session, seq_request.id) == []


def test_submit_unknown_is_404(client: TestClient, user_token: str):
    response = post_form(client, _path(999999), {"email": TEST_EMAIL}, token=user_token, htmx=True)

    assert response.status_code == 404


# ── Remove (DELETE) ──────────────────────────────────────────────────────────


def test_owner_removes_email_on_draft(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL, OTHER_EMAIL)

    response = delete(client, _remove_path(seq_request.id, TEST_EMAIL, "submit"), user_token, htmx=True)

    assert response.status_code == 200
    assert 'id="seq_request-share-emails-submit"' in response.text
    assert_flash(response, f"Email {TEST_EMAIL} removed.", category="success")
    assert _trigger(response)["shareEmailsChanged"] == {"context": "submit"}
    assert 'id="request-share-tab-count" hx-swap-oob="true"' in response.text
    assert _emails(session, seq_request.id) == [OTHER_EMAIL]


def test_owner_cannot_remove_after_submission(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL, OTHER_EMAIL, status=C.SeqRequestStatus.SUBMITTED)

    response = delete(client, _remove_path(seq_request.id, TEST_EMAIL), user_token, htmx=True)

    assert response.status_code == 403
    assert sorted(_emails(session, seq_request.id)) == sorted([TEST_EMAIL, OTHER_EMAIL])


def test_insider_removes_after_submission(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL, OTHER_EMAIL, status=C.SeqRequestStatus.SUBMITTED)

    response = delete(client, _remove_path(seq_request.id, TEST_EMAIL, "review"), insider_token, htmx=True)

    assert response.status_code == 200
    assert _emails(session, seq_request.id) == [OTHER_EMAIL]


def test_last_email_cannot_be_removed(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL)

    response = delete(client, _remove_path(seq_request.id, TEST_EMAIL), insider_token, htmx=True)

    assert response.status_code == 403
    assert _emails(session, seq_request.id) == [TEST_EMAIL]


def test_remove_review_context_denies_owner(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL, OTHER_EMAIL)

    response = delete(client, _remove_path(seq_request.id, TEST_EMAIL, "review"), user_token, htmx=True)

    assert response.status_code == 403
    assert len(_emails(session, seq_request.id)) == 2


def test_remove_unknown_email_is_404(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL, OTHER_EMAIL)

    response = delete(client, _remove_path(seq_request.id, "nobody@example.com"), user_token, htmx=True)

    assert response.status_code == 404


def test_remove_denies_stranger(client: TestClient, session: SyncSession, user, user_2_token: str):
    seq_request = _seq_request(session, user, TEST_EMAIL, OTHER_EMAIL)

    response = delete(client, _remove_path(seq_request.id, TEST_EMAIL), user_2_token, htmx=True)

    assert response.status_code == 403
    assert len(_emails(session, seq_request.id)) == 2
