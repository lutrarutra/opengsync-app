"""StoreSamplesAction: mark received samples, libraries, and pools as stored.

Behaviour follows legacy ``store_samples_workflow.select``:

- samples -> STORED; libraries -> STORED (POOLED ones stay POOLED); pools -> STORED;
  each gets ``timestamp_stored_utc``.
- afterwards each affected request moves on once everything it waits for is stored:
  raw samples -> SAMPLES_RECEIVED, pooled libraries -> PREPARED,
  unpooled libraries -> SAMPLES_RECEIVED. QC-only requests (FastAPI only, not in
  legacy) also set their libraries to QC_PENDING.
- an empty selection is rejected.
- started from a request page, every table is limited to that request and
  submitting returns to it.

Insider-only access is covered in ``server/test_action_access.py``.
"""

import json

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, actions, models, queries as Q, categories as C

from ...db.create_units import create_library, create_pool, create_project, create_sample, create_seq_request
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

PATH = "/htmx/actions/store-samples-action"


def _payload(samples=(), libraries=(), pools=()) -> dict[str, str]:
    return {
        "selected_sample_ids": json.dumps([s.id for s in samples]),
        "selected_library_ids": json.dumps([lib.id for lib in libraries]),
        "selected_pool_ids": json.dumps([p.id for p in pools]),
    }


def _request(session: SyncSession, user: models.User, submission_type: C.SubmissionType) -> models.SeqRequest:
    seq_request = create_seq_request(session, user, submission_type=submission_type)
    seq_request.status = C.SeqRequestStatus.ACCEPTED
    session.save(seq_request)
    return seq_request


def _library(session: SyncSession, user: models.User, seq_request: models.SeqRequest, status=C.LibraryStatus.ACCEPTED):
    library = create_library(session, user, seq_request)
    library.status = status
    session.save(library)
    return library


def _received_sample(session: SyncSession, user: models.User, seq_request: models.SeqRequest) -> models.Sample:
    """A raw sample waiting for delivery, linked to a library in the request."""
    sample = create_sample(session, user, create_project(session, user))
    sample.status = C.SampleStatus.WAITING_DELIVERY
    session.save(sample)
    actions.link_sample_library(session, sample.id, _library(session, user, seq_request).id)
    return sample


def _pool(session: SyncSession, user: models.User, seq_request: models.SeqRequest) -> models.Pool:
    pool = create_pool(session, user, seq_request)
    pool.status = C.PoolStatus.ACCEPTED
    session.save(pool)
    return pool


def _reload(session: SyncSession, model):
    session.expire_all()
    return session.get(type(model), model.id)


# ── Render ──────────────────────────────────────────────────────────────────


def test_render_shows_sample_library_and_pool_selection(client: TestClient, insider_token: str):
    response = get(client, PATH, insider_token)

    assert response.status_code == 200
    for field in ("selected_sample_ids", "selected_library_ids", "selected_pool_ids"):
        assert f'name="{field}"' in response.text, field
    assert 'name="csrf_token"' in response.text


def test_render_from_request_limits_every_table_and_posts_back(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    seq_request = create_seq_request(session, user)
    session.commit()

    response = get(client, PATH, insider_token, params={"seq_request_id": seq_request.id})

    assert response.status_code == 200
    body = response.text.replace("&amp;", "&")
    assert body.count(f"seq_request_id={seq_request.id}") >= 4  # three table URLs + the submit URL
    assert f'{PATH}?seq_request_id={seq_request.id}">Submit</button>' in body  # hx-post is an absolute URL


# ── Storing ─────────────────────────────────────────────────────────────────


def test_stores_samples_libraries_and_pools(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _request(session, user, C.SubmissionType.RAW_SAMPLES)
    sample = _received_sample(session, user, seq_request)
    library = _library(session, user, seq_request)
    pool = _pool(session, user, seq_request)
    session.commit()

    response = post_form(client, PATH, _payload([sample], [library], [pool]), token=insider_token)

    assert_htmx_redirect(response, "/")
    assert_flash(response, "Samples Stored!", category="success")
    sample, library, pool = _reload(session, sample), _reload(session, library), _reload(session, pool)
    assert sample.status == C.SampleStatus.STORED and sample.timestamp_stored_utc is not None
    assert library.status == C.LibraryStatus.STORED and library.timestamp_stored_utc is not None
    assert pool.status == C.PoolStatus.STORED and pool.timestamp_stored_utc is not None


def test_pooled_library_keeps_pooled_status(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _request(session, user, C.SubmissionType.POOLED_LIBRARIES)
    library = _library(session, user, seq_request, status=C.LibraryStatus.POOLED)
    session.commit()

    post_form(client, PATH, _payload(libraries=[library]), token=insider_token)

    library = _reload(session, library)
    assert library.status == C.LibraryStatus.POOLED
    assert library.timestamp_stored_utc is not None


def test_repeating_a_submission_is_harmless(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _request(session, user, C.SubmissionType.RAW_SAMPLES)
    sample = _received_sample(session, user, seq_request)
    session.commit()

    for _ in range(2):
        assert post_form(client, PATH, _payload([sample]), token=insider_token).status_code == 204

    assert _reload(session, sample).status == C.SampleStatus.STORED
    assert _reload(session, seq_request).status == C.SeqRequestStatus.SAMPLES_RECEIVED


# ── Request progression ─────────────────────────────────────────────────────


def test_raw_samples_request_is_received_once_all_samples_are_stored(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    seq_request = _request(session, user, C.SubmissionType.RAW_SAMPLES)
    first, second = _received_sample(session, user, seq_request), _received_sample(session, user, seq_request)
    session.commit()

    post_form(client, PATH, _payload([first]), token=insider_token)
    assert _reload(session, seq_request).status == C.SeqRequestStatus.ACCEPTED

    post_form(client, PATH, _payload([second]), token=insider_token)
    assert _reload(session, seq_request).status == C.SeqRequestStatus.SAMPLES_RECEIVED


def test_pooled_libraries_request_is_prepared_once_all_pools_are_stored(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    seq_request = _request(session, user, C.SubmissionType.POOLED_LIBRARIES)
    first, second = _pool(session, user, seq_request), _pool(session, user, seq_request)
    session.commit()

    post_form(client, PATH, _payload(pools=[first]), token=insider_token)
    assert _reload(session, seq_request).status == C.SeqRequestStatus.ACCEPTED

    post_form(client, PATH, _payload(pools=[second]), token=insider_token)
    assert _reload(session, seq_request).status == C.SeqRequestStatus.PREPARED


def test_unpooled_libraries_request_is_received_once_all_libraries_are_stored(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    seq_request = _request(session, user, C.SubmissionType.UNPOOLED_LIBRARIES)
    first, second = _library(session, user, seq_request), _library(session, user, seq_request)
    session.commit()

    post_form(client, PATH, _payload(libraries=[first]), token=insider_token)
    assert _reload(session, seq_request).status == C.SeqRequestStatus.ACCEPTED

    post_form(client, PATH, _payload(libraries=[second]), token=insider_token)
    assert _reload(session, seq_request).status == C.SeqRequestStatus.SAMPLES_RECEIVED


def test_qc_only_request_moves_libraries_to_qc_pending(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    """FastAPI-only branch; legacy had no QC-only handling here."""
    seq_request = _request(session, user, C.SubmissionType.QC_ONLY)
    first, second = _library(session, user, seq_request), _library(session, user, seq_request)
    session.commit()

    post_form(client, PATH, _payload(libraries=[first, second]), token=insider_token)

    assert _reload(session, seq_request).status == C.SeqRequestStatus.SAMPLES_RECEIVED
    assert _reload(session, first).status == C.LibraryStatus.QC_PENDING
    assert _reload(session, second).status == C.LibraryStatus.QC_PENDING


# ── Invalid input ───────────────────────────────────────────────────────────


def test_empty_selection_is_rejected(client: TestClient, insider_token: str):
    response = post_form(client, PATH, _payload(), token=insider_token)

    assert_form_invalid(response, contains="Select at least one sample, library, or pool.")


def test_unknown_id_changes_nothing(client: TestClient, session: SyncSession, user, insider_token: str):
    """A valid sample plus an unknown library: the sample must not be stored either."""
    seq_request = _request(session, user, C.SubmissionType.RAW_SAMPLES)
    sample = _received_sample(session, user, seq_request)
    session.commit()

    payload = _payload([sample])
    payload["selected_library_ids"] = json.dumps([999999])
    response = post_form(client, PATH, payload, token=insider_token)

    assert response.status_code == 404
    assert _reload(session, sample).status == C.SampleStatus.WAITING_DELIVERY
    assert _reload(session, seq_request).status == C.SeqRequestStatus.ACCEPTED


def test_csrf_mismatch_changes_nothing(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _request(session, user, C.SubmissionType.RAW_SAMPLES)
    sample = _received_sample(session, user, seq_request)
    session.commit()

    response = post_form_csrf_mismatch(client, PATH, _payload([sample]), token=insider_token)

    assert_form_invalid(response)
    assert _reload(session, sample).status == C.SampleStatus.WAITING_DELIVERY


# ── Redirect ────────────────────────────────────────────────────────────────


def test_submitting_from_a_request_returns_to_it(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _request(session, user, C.SubmissionType.RAW_SAMPLES)
    sample = _received_sample(session, user, seq_request)
    session.commit()

    response = post_form(
        client, PATH, _payload([sample]), token=insider_token, params={"seq_request_id": seq_request.id},
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")


def test_submitting_with_unknown_request_is_404(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _request(session, user, C.SubmissionType.RAW_SAMPLES)
    sample = _received_sample(session, user, seq_request)
    session.commit()

    response = post_form(client, PATH, _payload([sample]), token=insider_token, params={"seq_request_id": 999999})

    assert response.status_code == 404
    assert _reload(session, sample).status == C.SampleStatus.WAITING_DELIVERY
