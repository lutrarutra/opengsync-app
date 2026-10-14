"""LibraryAnnotationWorkflow: unfinished runs are listed when beginning, and can be resumed or discarded.

A run is registered (listed as unfinished) once its project is selected, and unregistered when
it is completed or discarded. Beginning the workflow lists the unfinished runs of the request,
most recently started first, instead of project selection; ``?new=true`` skips the list.
Insiders see and may continue or discard every run of the request, clients only the runs they
started. Every shown step refreshes the TTL of all of the run's keys, so a run expires as a unit,
one TTL after its last activity, which is also when it stops being listed.
"""

import json
import re
import time

from redis import Redis

from opengsync_db import SyncSession, models, categories as C

from ....db.create_units import create_seq_request, create_group
from ..._http import get, delete, post_form
from ._workflow import AnnotationWorkflow, HUMAN, spreadsheet_rows

PROJECT_SELECT = "project-select"
TTL_SECONDS = 7 * 24 * 3600  # RedisClient default


def _redis(client) -> Redis:
    return Redis(connection_pool=client.app.state.redis_pool)


def _index_key(seq_request_id: int) -> str:
    return f"WorkflowIndex:LibraryAnnotationWorkflow:seq_request:{seq_request_id}"


def _request(session: SyncSession, owner: models.User):
    seq_request = create_seq_request(session, owner, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    return seq_request


def _shared_request(session: SyncSession, owner: models.User, member: models.User):
    """A request both clients may write: ``member`` is in the request's group."""
    seq_request = _request(session, owner)
    group = create_group(session)
    session.add(models.links.UserAffiliation(user_id=member.id, group_id=group.id, affiliation_type=C.AffiliationType.MEMBER))
    seq_request.group = group
    session.commit()
    return seq_request


def _start(client, token: str, seq_request_id: int, title: str = "Unfinished project") -> AnnotationWorkflow:
    """A run left at sample annotation, i.e. right after selecting its project."""
    wf = AnnotationWorkflow(client, token, seq_request_id)
    wf.begin()
    wf.project(title)
    return wf


def _begin(client, token: str, seq_request_id: int, **params):
    response = get(client, f"/htmx/workflows/library-annotation/{seq_request_id}/begin", token, params=params)
    assert response.status_code == 200, response.text
    return response


def _listed(response) -> list[str]:
    """UUIDs of the listed runs, in order (each row has one 'Discard' button)."""
    return re.findall(r'hx-delete="[^"]*/unfinished/([0-9a-f-]+)"', response.text)


def _shows_project_selection(response) -> bool:
    return "Unfinished Annotations" not in response.text and "Select Project" in response.text


def _discard(client, token: str, seq_request_id: int, uuid: str):
    return delete(client, f"/htmx/workflows/library-annotation/{seq_request_id}/unfinished/{uuid}", token)


def _resume(client, token: str, seq_request_id: int, uuid: str):
    return get(client, f"/htmx/workflows/library-annotation/{seq_request_id}/resume", token, params={"uuid": uuid})


def _progress(response) -> list[tuple[int, str]]:
    """(steps completed, step label) of each listed run."""
    return [
        (int(count), label.strip())
        for count, label in re.findall(r'step[s]? completed">(\d+)</span>\s*([^<]+?)\s*</td>', response.text)
    ]


def _run_keys(client, uuid: str) -> list[bytes]:
    return _redis(client).keys(f"LibraryAnnotationWorkflow:{uuid}:*")


# ── Listing ─────────────────────────────────────────────────────────────────


def test_begin_shows_project_selection_without_unfinished_runs(client, session: SyncSession, user, user_token):
    seq_request = _request(session, user)

    assert _shows_project_selection(_begin(client, user_token, seq_request.id))


def test_begin_lists_the_started_run(client, session: SyncSession, user, user_token):
    seq_request = _request(session, user)
    wf = _start(client, user_token, seq_request.id, title="Listed project")

    response = _begin(client, user_token, seq_request.id)

    assert _listed(response) == [wf.uuid]
    assert "Listed project" in response.text
    assert user.name in response.text
    assert ">you</span>" in response.text
    assert _progress(response) == [(1, "Sample Annotation")]  # project selected, left at samples


def test_begin_new_skips_the_list(client, session: SyncSession, user, user_token):
    seq_request = _request(session, user)
    _start(client, user_token, seq_request.id)

    assert _shows_project_selection(_begin(client, user_token, seq_request.id, new=True))


def test_opening_project_selection_does_not_start_a_run(client, session: SyncSession, user, user_token):
    seq_request = _request(session, user)
    _begin(client, user_token, seq_request.id)  # modal opened and closed again

    assert _shows_project_selection(_begin(client, user_token, seq_request.id))


def test_runs_are_listed_most_recently_started_first(client, session: SyncSession, user, user_token):
    seq_request = _request(session, user)
    first = _start(client, user_token, seq_request.id, title="First project")
    second = _start(client, user_token, seq_request.id, title="Second project")
    first.samples([["Sample_1", HUMAN]])  # later activity on the first run does not reorder

    assert _listed(_begin(client, user_token, seq_request.id)) == [second.uuid, first.uuid]


def test_runs_of_other_requests_are_not_listed(client, session: SyncSession, user, user_token):
    request_a, request_b = _request(session, user), _request(session, user)
    _start(client, user_token, request_a.id)

    assert _shows_project_selection(_begin(client, user_token, request_b.id))


def test_completed_run_is_no_longer_listed(client, session: SyncSession, user, user_token):
    seq_request = _request(session, user)
    wf = _start(client, user_token, seq_request.id)
    wf.samples([["Sample_1", HUMAN]])
    wf.attributes(["Sample_1"])
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="complete-s-a-s")
    wf.complete()

    assert _shows_project_selection(_begin(client, user_token, seq_request.id))
    assert not _redis(client).zrange(_index_key(seq_request.id), 0, -1)


# ── Resuming ────────────────────────────────────────────────────────────────


def test_resume_shows_the_step_the_run_was_left_at(client, session: SyncSession, user, user_token):
    seq_request = _request(session, user)
    wf = _start(client, user_token, seq_request.id)
    wf.samples([["Sample_1", HUMAN]])

    listing = _begin(client, user_token, seq_request.id)
    assert f"/resume?uuid={wf.uuid}" in listing.text
    response = _resume(client, user_token, seq_request.id, wf.uuid)

    assert response.status_code == 200
    assert wf.rendered_step(response) == "sample-attribute-annotation"
    assert _progress(_begin(client, user_token, seq_request.id)) == [(2, "Sample Attributes")]
    # ... and the run goes on from there
    wf.attributes(["Sample_1"])
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="complete-s-a-s")
    wf.complete()


def test_run_left_after_back_resumes_prefilled(client, session: SyncSession, user, user_token):
    """A step reached via 'Back' resumes through its 'Previous' route, prefilled as submitted."""
    seq_request = _request(session, user)
    wf = _start(client, user_token, seq_request.id)
    wf.samples([["Prefilled_Sample", HUMAN]])
    wf.attributes(["Prefilled_Sample"])
    wf.back("sample-annotation")

    listing = _begin(client, user_token, seq_request.id)
    assert f"/sample-annotation?uuid={wf.uuid}" in listing.text
    assert f"/resume?uuid={wf.uuid}" not in listing.text
    assert _progress(listing) == [(1, "Sample Annotation")]  # steps after it no longer count
    response = get(client, f"{wf.prefix}/sample-annotation", user_token, params=wf.params)

    assert wf.rendered_step(response) == "sample-annotation"
    assert ["Prefilled_Sample", HUMAN] in [row[:2] for row in spreadsheet_rows(response)]


def test_resume_of_unknown_run_is_rejected(client, session: SyncSession, user, user_token):
    seq_request = _request(session, user)

    response = _resume(client, user_token, seq_request.id, "00000000-0000-0000-0000-000000000000")

    assert response.status_code == 400


def test_run_cannot_be_resumed_on_another_request(client, session: SyncSession, user, user_token):
    request_a, request_b = _request(session, user), _request(session, user)
    wf = _start(client, user_token, request_a.id)

    assert _resume(client, user_token, request_b.id, wf.uuid).status_code == 400


# ── Visibility: clients see their own runs, insiders every run ─────────────


def test_clients_see_and_continue_only_their_own_runs(client, session: SyncSession, user, user_token, user_2, user_2_token):
    seq_request = _shared_request(session, user, user_2)
    run_1 = _start(client, user_token, seq_request.id)
    run_2 = _start(client, user_2_token, seq_request.id)

    assert _listed(_begin(client, user_token, seq_request.id)) == [run_1.uuid]
    assert _listed(_begin(client, user_2_token, seq_request.id)) == [run_2.uuid]

    # The other client's run can't be resumed, posted to, or discarded by UUID either
    assert _resume(client, user_2_token, seq_request.id, run_1.uuid).status_code == 403
    assert get(client, f"{run_1.prefix}/sample-annotation", user_2_token, params=run_1.params).status_code == 403
    assert post_form(client, f"{run_1.prefix}/sample-annotation", {}, token=user_2_token, params=run_1.params).status_code == 403
    assert _discard(client, user_2_token, seq_request.id, run_1.uuid).status_code == 403
    assert _run_keys(client, run_1.uuid)


def test_insider_sees_every_run_with_who_started_it(client, session: SyncSession, user, user_token, insider, insider_token):
    seq_request = _request(session, user)
    client_run = _start(client, user_token, seq_request.id, title="Client project")
    insider_run = _start(client, insider_token, seq_request.id, title="Insider project")

    response = _begin(client, insider_token, seq_request.id)

    assert _listed(response) == [insider_run.uuid, client_run.uuid]
    rows = response.text.split("<tr>")[2:]  # header row first
    assert user.name in rows[1] and ">you</span>" not in rows[1]
    assert insider.name in rows[0] and ">you</span>" in rows[0]


def test_clients_do_not_see_runs_insiders_started(client, session: SyncSession, user, user_token, insider_token):
    """Even when the insider set the requestor as project owner."""
    seq_request = _request(session, user)
    wf = AnnotationWorkflow(client, insider_token, seq_request.id)
    wf.begin()
    wf.post(PROJECT_SELECT, {
        "new_project": "Insider started", "project_description": "d", "set_requestor_as_owner": "on",
    }, next_step="sample-annotation")

    assert _shows_project_selection(_begin(client, user_token, seq_request.id))
    assert _resume(client, user_token, seq_request.id, wf.uuid).status_code == 403


def test_insider_continues_a_clients_run(client, session: SyncSession, user, user_token, insider, insider_token):
    seq_request = _request(session, user)
    wf = _start(client, user_token, seq_request.id)
    wf.samples([["Stuck_Sample", HUMAN]])

    response = _resume(client, insider_token, seq_request.id, wf.uuid)
    assert response.status_code == 200
    assert wf.rendered_step(response) == "sample-attribute-annotation"

    support = AnnotationWorkflow(client, insider_token, seq_request.id)
    support.uuid, support.params = wf.uuid, wf.params
    support.attributes(["Stuck_Sample"])

    # Still the client's run, now last edited by the insider
    listing = _begin(client, user_token, seq_request.id)
    assert _listed(listing) == [wf.uuid]
    assert f"by {insider.name}" in listing.text


def test_someone_else_active_recently_is_warned_about(client, session: SyncSession, user, user_token, insider, insider_token):
    seq_request = _request(session, user)
    wf = _start(client, user_token, seq_request.id)

    insider_listing = _begin(client, insider_token, seq_request.id)
    assert f"{user.name} was active less than a minute ago" in insider_listing.text
    assert "might still be working on this annotation" in insider_listing.text  # confirm before continuing

    own_listing = _begin(client, user_token, seq_request.id)  # own activity is no warning
    assert "might still be working on" not in own_listing.text

    # Activity long enough ago is no warning either
    r = _redis(client)
    key = f"LibraryAnnotationWorkflow:{wf.uuid}:run"
    run = json.loads(r.get(key))
    run["last_active_at"] = time.time() - 16 * 60
    r.set(key, json.dumps(run))
    assert "might still be working on" not in _begin(client, insider_token, seq_request.id).text


# ── Discarding ──────────────────────────────────────────────────────────────


def test_discard_removes_the_run_and_lists_the_rest(client, session: SyncSession, user, user_token):
    seq_request = _request(session, user)
    first = _start(client, user_token, seq_request.id, title="First project")
    second = _start(client, user_token, seq_request.id, title="Second project")

    response = _discard(client, user_token, seq_request.id, first.uuid)

    assert response.status_code == 200
    assert _listed(response) == [second.uuid]
    assert _run_keys(client, first.uuid) == []

    response = _discard(client, user_token, seq_request.id, second.uuid)  # the last one

    assert response.status_code == 200
    assert _shows_project_selection(response)
    assert _run_keys(client, second.uuid) == []
    assert not _redis(client).zrange(_index_key(seq_request.id), 0, -1)


def test_insider_discards_a_clients_run(client, session: SyncSession, user, user_token, insider_token):
    seq_request = _request(session, user)
    wf = _start(client, user_token, seq_request.id)

    assert _discard(client, insider_token, seq_request.id, wf.uuid).status_code == 200
    assert _run_keys(client, wf.uuid) == []
    assert _shows_project_selection(_begin(client, user_token, seq_request.id))


def test_discarding_an_unknown_run_is_rejected(client, session: SyncSession, user, user_token):
    request_a, request_b = _request(session, user), _request(session, user)
    wf = _start(client, user_token, request_a.id)

    assert _discard(client, user_token, request_b.id, wf.uuid).status_code == 400  # run of another request
    assert _discard(client, user_token, request_a.id, "00000000-0000-0000-0000-000000000000").status_code == 400
    assert _run_keys(client, wf.uuid)


# ── Going back to project selection ─────────────────────────────────────────


def _resubmit_project_select(client, token: str, wf: AnnotationWorkflow, title: str):
    """What 'Back' to project selection and 'Next' does in the UI: the post has no UUID."""
    back = get(client, f"{wf.prefix}/{PROJECT_SELECT}", token, params=wf.params)
    assert f'value="{wf.uuid}"' in back.text  # the run it was reached from
    return post_form(client, f"{wf.prefix}/{PROJECT_SELECT}", {
        "new_project": title, "project_description": "d", "replaces_uuid": wf.uuid,
    }, token=token)


def test_resubmitting_project_selection_replaces_the_run(client, session: SyncSession, user, user_token):
    seq_request = _request(session, user)
    wf = _start(client, user_token, seq_request.id, title="Old title")
    wf.samples([["Sample_1", HUMAN]])

    response = _resubmit_project_select(client, user_token, wf, "New title")

    assert response.status_code == 200
    listing = _begin(client, user_token, seq_request.id)
    [new_uuid] = _listed(listing)
    assert new_uuid != wf.uuid
    assert "New title" in listing.text
    assert _run_keys(client, wf.uuid) == []


def test_replaced_run_keeps_who_started_it(client, session: SyncSession, user, user_token, insider_token):
    """Support redoing a client's project selection leaves the run the client's."""
    seq_request = _request(session, user)
    wf = _start(client, user_token, seq_request.id)
    started_listing = _begin(client, user_token, seq_request.id)

    _resubmit_project_select(client, insider_token, wf, "Fixed by support")

    listing = _begin(client, user_token, seq_request.id)
    assert len(_listed(listing)) == 1
    assert "Fixed by support" in listing.text
    started_at = re.search(r"<td>(\d{4}-\d\d-\d\d \d\d:\d\d)</td>", started_listing.text)
    assert started_at is not None and f"<td>{started_at.group(1)}</td>" in listing.text


# ── Expiry ──────────────────────────────────────────────────────────────────


def test_expired_runs_are_not_listed(client, session: SyncSession, user, user_token):
    seq_request = _request(session, user)
    wf = _start(client, user_token, seq_request.id)
    r = _redis(client)
    r.zadd(_index_key(seq_request.id), {wf.uuid: time.time() - TTL_SECONDS - 1})

    assert _shows_project_selection(_begin(client, user_token, seq_request.id))
    assert not r.zrange(_index_key(seq_request.id), 0, -1)


def test_runs_whose_state_is_gone_are_not_listed(client, session: SyncSession, user, user_token):
    seq_request = _request(session, user)
    wf = _start(client, user_token, seq_request.id)
    r = _redis(client)
    r.delete(*_run_keys(client, wf.uuid))  # e.g. flushed

    assert _shows_project_selection(_begin(client, user_token, seq_request.id))
    assert not r.zrange(_index_key(seq_request.id), 0, -1)


def test_activity_keeps_every_key_of_the_run_alive(client, session: SyncSession, user, user_token):
    """Keys written once (the header, at project selection) don't expire before the rest."""
    seq_request = _request(session, user)
    wf = _start(client, user_token, seq_request.id)
    r = _redis(client)
    header = f"LibraryAnnotationWorkflow:{wf.uuid}:header"
    r.expire(header, 60)

    wf.samples([["Sample_1", HUMAN]])

    assert r.ttl(header) > 3600
    assert r.ttl(_index_key(seq_request.id)) > 3600
