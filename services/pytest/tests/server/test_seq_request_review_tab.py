"""Seq request page: placement of the insider 'Review' tab across request statuses."""

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, categories as C

from ..db.create_units import create_seq_request, create_library
from ._http import get, flush_redis

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
