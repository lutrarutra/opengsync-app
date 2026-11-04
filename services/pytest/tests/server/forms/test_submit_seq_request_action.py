"""SubmitSeqRequestAction: render, permissions, validation, and submission.

Access control:
- **Init()** requires WRITE on the seq request (owner / insider / admin).
- **GET (Render)** has no extra auth — anyone with WRITE can view.
- **POST (Submit)** is open to anyone with WRITE; non-insiders additionally
  need ``is_submittable()`` (at least one library, a signed auth form and a share email).
- Only DRAFT seq requests can be submitted.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C
from server.core import config
from server.core.config import SampleSubmissionWindow

from ...db.create_units import create_file, create_library, create_seq_request
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
    session: SyncSession, user: models.User, share_email: bool = True,
) -> models.SeqRequest:
    """Create a DRAFT seq request with one library and a share email (submittable once the auth form is attached)."""
    seq_request = create_seq_request(session, user)
    create_library(session, user, seq_request)
    if share_email:
        seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(email="share@example.com"))
        session.save(seq_request)
    session.commit()
    return seq_request


def _attach_auth_form(session: SyncSession, seq_request: models.SeqRequest) -> None:
    auth_form = create_file(session, seq_request=seq_request)
    auth_form.type = C.MediaFileType.SEQ_AUTH_FORM
    session.commit()


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


def test_submit_allows_owner(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    seq_request = _seq_request_with_library(session, user)
    _attach_auth_form(session, seq_request)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(samples_delivered_by_mail="on"),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert updated.status == C.SeqRequestStatus.SUBMITTED
    assert all(library.status == C.LibraryStatus.SUBMITTED for library in updated.libraries)


def test_submit_owner_without_auth_form_is_400(
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

    assert response.status_code == 400
    assert session.first(
        Q.seq_request.select(id=seq_request.id)
    ).status == C.SeqRequestStatus.DRAFT


def test_submit_owner_without_share_email_is_400(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    seq_request = _seq_request_with_library(session, user, share_email=False)
    _attach_auth_form(session, seq_request)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(samples_delivered_by_mail="on"),
        token=user_token,
    )

    assert response.status_code == 400
    session.expire_all()
    assert session.first(
        Q.seq_request.select(id=seq_request.id)
    ).status == C.SeqRequestStatus.DRAFT


def test_submit_insider_without_share_email_is_allowed(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    """Insiders can still submit on the customer's behalf."""
    seq_request = _seq_request_with_library(session, user, share_email=False)
    _attach_auth_form(session, seq_request)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(samples_delivered_by_mail="on"),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")


def test_submit_denied_for_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    seq_request = _seq_request_with_library(session, user)
    _attach_auth_form(session, seq_request)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(samples_delivered_by_mail="on"),
        token=user_2_token,
    )

    assert response.status_code == 403
    assert session.first(
        Q.seq_request.select(id=seq_request.id)
    ).status == C.SeqRequestStatus.DRAFT


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
    """An unchecked ``samples_delivered_by_mail`` checkbox (sent empty or not at all) is False,
    so a sample submission time alone submits the request. (Was rejected as "required" until
    missing/empty booleans were treated as unchecked, 2026-10-13.)"""
    seq_request = _seq_request_with_library(session, user)

    response = post_form(
        client,
        _submit_path(seq_request.id),
        _payload(
            samples_delivered_by_mail="",
            sample_submission_time=_next(2, 16).strftime("%Y-%m-%d %H:%M"),  # future: past times are rejected
        ),
        token=insider_token,
    )

    assert response.status_code == 204, response.text
    session.expire_all()
    assert session.first(
        Q.seq_request.select(id=seq_request.id)
    ).status == C.SeqRequestStatus.SUBMITTED


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
            sample_submission_time=_next(2, 16).strftime("%Y-%m-%d %H:%M"),  # future: past times are rejected
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

# ── Sample submission time (legacy parity; customer test 2026-11-04) ─────────
# Legacy rejected past times and times outside the submission windows and stored the time as a
# SAMPLE_SUBMISSION event; the FastAPI port had dropped all three.

@pytest.fixture
def windows(monkeypatch):
    """Wednesday 15-17 and Friday 13-15, as in opengsync.yaml."""
    monkeypatch.setattr(config.settings.app_config, "sample_submission_windows", [
        SampleSubmissionWindow(weekday=2, start_time=dt.time(15), end_time=dt.time(17)),
        SampleSubmissionWindow(weekday=4, start_time=dt.time(13), end_time=dt.time(15)),
    ])


def _next(weekday: int, hour: int) -> dt.datetime:
    """Local naive datetime of the next given weekday (at least a day ahead), as the picker sends it."""
    today = config.settings.now().date()
    days = (weekday - today.weekday()) % 7 or 7
    return dt.datetime.combine(today + dt.timedelta(days=days), dt.time(hour))


def _submittable(session: SyncSession, user) -> models.SeqRequest:
    seq_request = _seq_request_with_library(session, user)
    _attach_auth_form(session, seq_request)
    return seq_request


def _submit_at(client, token, seq_request, moment: dt.datetime, custom: bool = False):
    return post_form(client, _submit_path(seq_request.id), {
        "sample_submission_time": moment.strftime("%Y-%m-%dT%H:%M"),
        "custom_sample_submission_time": "on" if custom else "",
        "comment": "",
    }, token=token)


def test_submission_time_in_the_past_is_rejected(client: TestClient, session: SyncSession, user, user_token: str, windows):
    seq_request = _submittable(session, user)
    response = _submit_at(client, user_token, seq_request, dt.datetime(2020, 1, 1, 16))
    assert_form_invalid(response)
    assert "cannot be in the past" in response.text
    session.expire_all()
    assert session.get_one(Q.seq_request.select(id=seq_request.id)).status == C.SeqRequestStatus.DRAFT


def test_submission_time_outside_windows_is_rejected(client: TestClient, session: SyncSession, user, user_token: str, windows):
    seq_request = _submittable(session, user)
    response = _submit_at(client, user_token, seq_request, _next(0, 10))  # Monday 10:00
    assert_form_invalid(response)
    assert "within the allowed submission times" in response.text
    assert 'name="custom_sample_submission_time"' in response.text


def test_custom_time_outside_windows_is_accepted(client: TestClient, session: SyncSession, user, user_token: str, windows):
    seq_request = _submittable(session, user)
    assert_htmx_redirect(_submit_at(client, user_token, seq_request, _next(0, 10), custom=True))


def test_submission_time_in_window_creates_event(client: TestClient, session: SyncSession, user, user_token: str, windows):
    seq_request = _submittable(session, user)
    moment = _next(2, 16)  # Wednesday 16:00 local

    assert_htmx_redirect(_submit_at(client, user_token, seq_request, moment))

    session.expire_all()
    stored = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert stored.status == C.SeqRequestStatus.SUBMITTED
    event = stored.sample_submission_event
    assert event is not None and event.type == C.EventType.SAMPLE_SUBMISSION
    assert event.timestamp_utc == moment.replace(tzinfo=config.settings.TIMEZONE).astimezone(dt.timezone.utc)


def test_delivery_by_mail_creates_no_event(client: TestClient, session: SyncSession, user, user_token: str, windows):
    seq_request = _submittable(session, user)
    assert_htmx_redirect(post_form(client, _submit_path(seq_request.id), _payload(), token=user_token))
    session.expire_all()
    assert session.get_one(Q.seq_request.select(id=seq_request.id)).sample_submission_event is None


def test_submit_form_lists_weekday_names(client: TestClient, session: SyncSession, user, user_token: str, windows):
    from server.core.templates import j2
    j2.env.globals["sample_submission_windows"] = config.settings.app_config.sample_submission_windows
    seq_request = _seq_request_with_library(session, user)
    text = get(client, _render_path(seq_request.id), user_token).text
    assert "Wednesday" in text and "Friday" in text
    assert '<span class="badge">2</span>' not in text
