"""Seq request page: placement of the insider 'Review' tab across request statuses."""

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, categories as C

from ..db.create_units import create_seq_request, create_library
from ._http import get, post_form, flush_redis, assert_htmx_redirect

REVIEW_TAB = 'data-bs-target="#request-review-tab"'
DATA_TAB = 'data-bs-target="#request-data_paths-tab"'
CHECKLIST_TAB = 'data-bs-target="#request-checklist-tab"'
PROCESS_BUTTON = "Process Request"


def _page(client: TestClient, session: SyncSession, user, token: str, status: C.SeqRequestStatus) -> str:
    seq_request = create_seq_request(session, user)
    seq_request.status = status
    session.save(seq_request)
    session.commit()
    flush_redis(client)
    response = get(client, f"/seq_requests/{seq_request.id}", token)
    assert response.status_code == 200
    return response.text


def test_submitted_review_tab_first_and_active(client: TestClient, session: SyncSession, user, insider_token: str):
    html = _page(client, session, user, insider_token, C.SeqRequestStatus.SUBMITTED)
    assert html.index(REVIEW_TAB) < html.index(CHECKLIST_TAB)
    assert 'class="tab-pane fade show active" id="request-review-tab"' in html
    assert PROCESS_BUTTON in html


@pytest.mark.parametrize("status", [  # type: ignore[attr-defined]
    C.SeqRequestStatus.ACCEPTED,
    C.SeqRequestStatus.SAMPLES_RECEIVED,
    C.SeqRequestStatus.FINISHED,
    C.SeqRequestStatus.REJECTED,
])
def test_reviewed_request_keeps_review_tab_last(
    client: TestClient, session: SyncSession, user, insider_token: str, status: C.SeqRequestStatus,
):
    html = _page(client, session, user, insider_token, status)
    assert html.count(REVIEW_TAB) == 1
    assert html.index(REVIEW_TAB) > html.index(DATA_TAB)
    assert 'class="tab-pane fade " id="request-review-tab"' in html
    assert 'class="tab-pane fade show active" id="request-checklist-tab"' in html
    assert PROCESS_BUTTON not in html


def test_draft_request_has_no_review_tab(client: TestClient, session: SyncSession, user, insider_token: str):
    html = _page(client, session, user, insider_token, C.SeqRequestStatus.DRAFT)
    assert REVIEW_TAB not in html


def test_client_never_sees_review_tab(client: TestClient, session: SyncSession, user, user_token: str):
    html = _page(client, session, user, user_token, C.SeqRequestStatus.ACCEPTED)
    assert REVIEW_TAB not in html


MANUAL_STEPS = [
    "technical_requirements", "check_contacts", "auth_form_checked", "check_comments",
    "check_submission_date", "check_overview", "samples_checked", "check_libraries",
]


def _review_count(html: str) -> str:
    button = html[html.index(REVIEW_TAB):]
    button = button[:button.index("</button>")]
    return button[button.index('<span class="tab-count'):]


def test_raw_samples_count_skips_not_relevant_steps(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    seq_request.status = C.SeqRequestStatus.ACCEPTED
    seq_request.review_checklist = {step: True for step in MANUAL_STEPS}
    session.save(seq_request)
    session.commit()
    flush_redis(client)

    html = get(client, f"/seq_requests/{seq_request.id}", insider_token).text

    assert _review_count(html) == '<span class="tab-count tab-count-done">9/9</span>'


def test_libraries_without_mux_skip_multiplexing_step(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    create_library(session, user, seq_request)
    session.commit()
    flush_redis(client)

    html = get(client, f"/seq_requests/{seq_request.id}", insider_token).text

    assert _review_count(html).endswith("/11</span>")


def test_mux_libraries_keep_multiplexing_step(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    create_library(session, user, seq_request).mux_type = C.MUXType.TENX_OLIGO
    session.commit()
    flush_redis(client)

    html = get(client, f"/seq_requests/{seq_request.id}", insider_token).text

    assert _review_count(html).endswith("/12</span>")


# ── Manual check history ─────────────────────────────────────────────────────

def _logs(session: SyncSession, seq_request_id: int) -> list[models.ChecklistLog]:
    session.expire_all()
    return list(session.execute(
        sa.select(models.ChecklistLog).where(models.ChecklistLog.seq_request_id == seq_request_id).order_by(models.ChecklistLog.id)
    ).scalars())


def _toggle(client: TestClient, seq_request_id: int, action: str, step: str, token: str):
    return post_form(client, f"/htmx/seq_requests/{seq_request_id}/{action}/{step}", {}, token=token, htmx=True)


def test_check_and_uncheck_are_logged(client: TestClient, session: SyncSession, insider, insider_token: str):
    seq_request = create_seq_request(session, insider)
    session.commit()

    assert_htmx_redirect(_toggle(client, seq_request.id, "review-check", "check_overview", insider_token), f"/seq_requests/{seq_request.id}")
    # Checking an already checked step changes nothing and is not logged again
    assert_htmx_redirect(_toggle(client, seq_request.id, "review-check", "check_overview", insider_token), f"/seq_requests/{seq_request.id}")
    assert_htmx_redirect(_toggle(client, seq_request.id, "review-uncheck", "check_overview", insider_token), f"/seq_requests/{seq_request.id}")

    logs = _logs(session, seq_request.id)
    assert [(log.step, log.checked) for log in logs] == [("check_overview", True), ("check_overview", False)]
    assert all(log.actor_id == insider.id for log in logs)
    assert all(log.checklist_type == C.ChecklistType.SEQ_REQUEST_REVIEW for log in logs)
    assert logs[0].timestamp_utc <= logs[1].timestamp_utc


@pytest.mark.parametrize("action", ["review-check", "review-uncheck"])  # type: ignore[attr-defined]
def test_unknown_review_step_rejected(client: TestClient, session: SyncSession, insider, insider_token: str, action: str):
    seq_request = create_seq_request(session, insider)
    session.commit()

    assert _toggle(client, seq_request.id, action, "not_a_step", insider_token).status_code == 400

    assert _logs(session, seq_request.id) == []
    assert "not_a_step" not in (session.get_one(sa.select(models.SeqRequest).where(models.SeqRequest.id == seq_request.id)).review_checklist or {})


def test_review_checklist_shows_history(client: TestClient, session: SyncSession, insider, insider_token: str):
    seq_request = create_seq_request(session, insider)
    session.commit()
    _toggle(client, seq_request.id, "review-check", "check_contacts", insider_token)

    response = get(client, f"/htmx/seq_requests/{seq_request.id}/review-checklist", insider_token, htmx=True)
    assert response.status_code == 200
    html = response.text
    assert 'data-bs-target="#request-review-check_contacts-history"' in html
    assert "bi-clock-history" in html
    assert f"checked by {insider.name}" in html
    # The overview opens as a popup on the same page
    assert 'data-bs-target="#request-overview"' in html
    assert "tab=request-overview" not in html


def test_checklist_log_deleted_with_request(client: TestClient, session: SyncSession, insider, insider_token: str):
    seq_request = create_seq_request(session, insider)
    session.commit()
    seq_request_id = seq_request.id
    _toggle(client, seq_request_id, "review-check", "check_comments", insider_token)
    assert len(_logs(session, seq_request_id)) == 1

    session.delete(session.get_one(sa.select(models.SeqRequest).where(models.SeqRequest.id == seq_request_id)))
    session.commit()

    assert _logs(session, seq_request_id) == []
