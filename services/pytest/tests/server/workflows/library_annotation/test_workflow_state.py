"""LibraryAnnotationWorkflow: Redis state is bound to the request the run was started for.

State lives under ``LibraryAnnotationWorkflow:{uuid}:*``. ``require_seq_request_write``
only checks the request in the URL, so a run (UUID) is bound to its request at project
selection (``header["seq_request_id"]``) and every step rejects a run that is bound to
another request (400). Every step except project selection also rejects a run with no
state: never started, or expired (400). A rejected attempt leaves the run untouched.

Project selection posts without the UUID (as legacy ``select_project``), so going back to
it and submitting starts a new run.
"""

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, get, libraries_by_name

L = C.LibraryType
EXPIRED = "This annotation has expired. Please start again."
FOREIGN = "This annotation belongs to another sequencing request."
# Every step a run at the review step has passed, plus the review step itself.
REACHED_STEPS = ["project-select", "sample-annotation", "sample-attribute-annotation", "select-service", "complete-s-a-s"]


def _at_review(client, session: SyncSession, owner, token: str, title: str = "State project"):
    seq_request = create_seq_request(session, owner, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    wf = AnnotationWorkflow(client, token, seq_request.id)
    wf.begin()
    wf.project(title)
    wf.samples([["State_1", HUMAN]])
    wf.attributes(["State_1"])
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="complete-s-a-s")
    return seq_request, wf


def _redis(client) -> Redis:
    return Redis(connection_pool=client.app.state.redis_pool)


def _snapshot(client, uuid: str) -> dict:
    r = _redis(client)
    return {key: r.dump(key) for key in sorted(r.keys(f"LibraryAnnotationWorkflow:{uuid}:*"))}


def _on(wf: AnnotationWorkflow, seq_request_id: int, token: str | None = None) -> AnnotationWorkflow:
    """The same UUID, used on another request (and optionally by another user)."""
    other = AnnotationWorkflow(TestClient(wf.client.app, raise_server_exceptions=False), token or wf.token, seq_request_id)
    other.uuid = wf.uuid
    other.params = {"uuid": wf.uuid}
    return other


def _get(wf: AnnotationWorkflow, step: str):
    return wf.client.get(f"{wf.prefix}/{step}", params=wf.params, cookies={"access_token": wf.token})


def _assert_rejected(response, message: str) -> None:
    assert response.status_code == 400, f"expected 400, got {response.status_code}"
    assert message in response.text


# ── Project selection ───────────────────────────────────────────────────────


def test_back_to_project_select_prefills_and_starts_a_new_run(client, session: SyncSession, user, user_token):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Prefilled project title", description="kept on back")

    back = get(client, f"{wf.prefix}/project-select", user_token, params=wf.params)

    assert back.status_code == 200
    assert "Prefilled project title" in back.text
    assert "kept on back" in back.text
    assert f'hx-post="http://testserver{wf.prefix}/project-select"' in back.text  # no ?uuid=


def test_project_selection_binds_the_run_to_its_request(client, session: SyncSession, user, user_token):
    seq_request, wf = _at_review(client, session, user, user_token)

    header = _redis(client).keys(f"LibraryAnnotationWorkflow:{wf.uuid}:header*")
    assert header, "no header saved for the run"
    wf.complete()  # the bound request is the one in the URL: completes normally
    assert len(libraries_by_name(session, seq_request.id)) == 1


# ── Missing or expired state ────────────────────────────────────────────────


@pytest.mark.parametrize("step", REACHED_STEPS[1:])
def test_unknown_uuid_is_rejected_on_every_step(client, session: SyncSession, user, user_token, step: str):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    wf = _on(AnnotationWorkflow(client, user_token, seq_request.id), seq_request.id)  # fresh UUID, never begun

    _assert_rejected(wf.post(step, {}, status=None), EXPIRED)
    if step != "complete-s-a-s":  # the review step has no 'Back' route
        _assert_rejected(_get(wf, step), EXPIRED)
    assert session.count(Q.library.select(seq_request_id=seq_request.id)) == 0


def test_unknown_uuid_may_start_at_project_selection(client, session: SyncSession, user, user_token):
    """Project selection is where a run starts, so a UUID without state is fine there."""
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    wf = AnnotationWorkflow(client, user_token, seq_request.id)

    wf.begin()
    wf.project("Fresh run project")


def test_expired_state_is_rejected(client, session: SyncSession, user, user_token):
    seq_request, wf = _at_review(client, session, user, user_token, title="Expired state project")
    _redis(client).delete(*_snapshot(client, wf.uuid))  # TTL ran out

    _assert_rejected(_on(wf, seq_request.id).post("complete-s-a-s", status=None), EXPIRED)

    session.expire_all()
    assert session.count(Q.library.select(seq_request_id=seq_request.id)) == 0
    assert session.first(Q.project.select(title="Expired state project")) is None


# ── UUID reuse across requests and users ────────────────────────────────────


def test_uuid_cannot_be_completed_on_another_request(client, session: SyncSession, user, user_token):
    """The owner's second request is writable, but this run belongs to the first one."""
    request_a, wf = _at_review(client, session, user, user_token, title="Run of request A")
    request_b = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    before = _snapshot(client, wf.uuid)

    _assert_rejected(_on(wf, request_b.id).post("complete-s-a-s", status=None), FOREIGN)

    assert session.count(Q.library.select(seq_request_id=request_b.id)) == 0
    assert _snapshot(client, wf.uuid) == before  # the run is untouched...
    wf.complete()  # ...and still completes on its own request
    assert set(libraries_by_name(session, request_a.id)) == {f"State_1_{L.BULK_RNA_SEQ.identifier}"}


@pytest.mark.parametrize("step", REACHED_STEPS)
def test_every_step_rejects_a_run_of_another_request(client, session: SyncSession, user, user_token, step: str):
    """GET ('Back') and POST of every step, including project selection, which would re-bind it."""
    _, wf = _at_review(client, session, user, user_token, title="Run bound to A")
    request_b = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    before = _snapshot(client, wf.uuid)
    other = _on(wf, request_b.id)

    if step != "complete-s-a-s":  # the review step has no 'Back' route
        back = _get(other, step)
        _assert_rejected(back, FOREIGN)
        assert "State_1" not in back.text and "Run bound to A" not in back.text
    _assert_rejected(other.post(step, {"new_project": "Hijack", "project_description": "x"}, status=None), FOREIGN)

    assert _snapshot(client, wf.uuid) == before


def test_uuid_cannot_be_used_by_another_user_on_their_request(
    client, session: SyncSession, user, user_2, user_token, user_2_token,
):
    _, wf = _at_review(client, session, user, user_token, title="Run of user 1")
    foreign = create_seq_request(session, user_2, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    before = _snapshot(client, wf.uuid)
    leaked = _on(wf, foreign.id, token=user_2_token)

    # user_2 has WRITE on their own request, but must neither see user 1's annotation...
    previous = _get(leaked, "sample-attribute-annotation")
    _assert_rejected(previous, FOREIGN)
    assert "State_1" not in previous.text
    # ...nor import it into their request.
    _assert_rejected(leaked.post("complete-s-a-s", status=None), FOREIGN)

    session.expire_all()
    assert session.count(Q.library.select(seq_request_id=foreign.id)) == 0
    assert session.first(Q.project.select(title="Run of user 1")) is None
    assert _snapshot(client, wf.uuid) == before


def test_stranger_cannot_read_the_owners_run(client, session: SyncSession, user, user_token, user_2_token):
    """On the owner's request, ``require_seq_request_write`` already stops a stranger (403)."""
    seq_request, wf = _at_review(client, session, user, user_token)

    stranger = _on(wf, seq_request.id, token=user_2_token)
    for step in ("sample-annotation", "sample-attribute-annotation", "select-service"):
        assert _get(stranger, step).status_code == 403, step
    assert stranger.post("complete-s-a-s", status=None).status_code == 403
