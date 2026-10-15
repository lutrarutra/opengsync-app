"""Status tab (staff only) on request, project, lab prep and experiment pages."""
import re

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C
from opengsync_db.transitions import run_operation, routes as transition_routes

from ..db.create_units import create_seq_request, create_library, create_project, create_lab_prep, create_experiment
from ._http import get, post_form


def _objects(session: SyncSession, user) -> dict[str, tuple[str, str, int]]:
    seq_request = create_seq_request(session, user)
    create_library(session, user, seq_request)
    project = create_project(session, user)
    lab_prep = create_lab_prep(session, user)
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    session.commit()
    return {
        "seq_request": (f"/seq_requests/{seq_request.id}", "request-status-tab", seq_request.id),
        "project": (f"/projects/{project.id}", "project-status-tab", project.id),
        "lab_prep": (f"/lab_preps/{lab_prep.id}", "lab_prep-status-tab", lab_prep.id),
        "experiment": (f"/experiments/{experiment.id}", "experiment-status-tab", experiment.id),
    }


@pytest.mark.parametrize("entity", ["seq_request", "project", "lab_prep", "experiment"])
def test_tab_and_content_for_insider(client: TestClient, session: SyncSession, user, insider, insider_token: str, entity: str):
    page, tab_id, obj_id = _objects(session, insider)[entity]

    response = get(client, page, insider_token)
    assert response.status_code == 200
    assert f'data-bs-target="#{tab_id}"' in response.text
    assert f"/htmx/status/{entity}/{obj_id}" in response.text

    content = get(client, f"/htmx/status/{entity}/{obj_id}", insider_token, htmx=True)
    assert content.status_code == 200, content.text
    assert "status-next-title" in content.text or "nothing left to do" in content.text
    history = get(client, f"/htmx/status/{entity}/{obj_id}/history", insider_token, htmx=True)
    assert history.status_code == 200


def test_tab_hidden_and_routes_denied_for_client(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = create_seq_request(session, user)
    session.commit()

    page = get(client, f"/seq_requests/{seq_request.id}", user_token)
    assert page.status_code == 200
    assert "request-status-tab" not in page.text
    assert get(client, f"/htmx/status/seq_request/{seq_request.id}", user_token, htmx=True).status_code == 403
    assert get(client, f"/htmx/status/seq_request/{seq_request.id}/history", user_token, htmx=True).status_code == 403


def test_unknown_entity_and_record(client: TestClient, insider_token: str):
    assert get(client, "/htmx/status/sample/1", insider_token, htmx=True).status_code == 404
    assert get(client, "/htmx/status/seq_request/999999", insider_token, htmx=True).status_code == 404


def test_content_shows_next_step_and_blockers(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    seq_request.status = C.SeqRequestStatus.SAMPLES_RECEIVED
    for library_status in (C.LibraryStatus.POOLED, C.LibraryStatus.ACCEPTED):
        library = create_library(session, user, seq_request)
        library.status = library_status
    session.commit()

    text = get(client, f"/htmx/status/seq_request/{seq_request.id}", insider_token, htmx=True).text
    assert "Raw samples, in-house library prep" in text
    assert re.search(r'class="status-next-title[^"]*"[^>]*>Library prep<', text)
    assert "1 ACCEPTED among the libraries of the request" in text  # blocker text (tooltip)
    assert "1/2" in text and "1 accepted still" in text  # as a progress bar: 1 of 2 libraries fine
    assert "on the lab prep page: Add libraries to lab prep" in text
    assert 'data-operation="worker.request_prepared"' in text  # under "Other status changes"
    assert "Unarchive" not in text  # does not apply to this status


def test_history_shows_actor_and_comment(client: TestClient, session: SyncSession, user, insider, insider_token: str):
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    session.commit()
    with run_operation(session, "manual.edit_library", actor_id=insider.id, comment="wrong sample sheet"):
        library.status = C.LibraryStatus.FAILED
    session.commit()

    text = get(client, f"/htmx/status/seq_request/{seq_request.id}/history", insider_token, htmx=True).text
    assert "Edit library" not in text  # the edit did not touch the request itself

    project = create_project(session, user)
    session.commit()
    with run_operation(session, "manual.edit_project", actor_id=insider.id, comment="wrong sample sheet"):
        project.status = C.ProjectStatus.ARCHIVED
    session.commit()
    text = get(client, f"/htmx/status/project/{project.id}/history", insider_token, htmx=True).text
    assert "Edit project" in text
    assert insider.name in text
    assert "wrong sample sheet" in text


def test_route_override(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    response = post_form(client, f"/htmx/status/seq_request/{seq_request.id}/route", {"route": "pooled_libraries"}, token=insider_token)
    assert response.status_code == 204
    session.expire_all()
    assert session.get_one(Q.seq_request.select(id=seq_request.id)).route_override == "pooled_libraries"
    assert "Pre-pooled libraries" in get(client, f"/htmx/status/seq_request/{seq_request.id}", insider_token, htmx=True).text

    post_form(client, f"/htmx/status/seq_request/{seq_request.id}/route", {"route": ""}, token=insider_token)
    session.expire_all()
    assert session.get_one(Q.seq_request.select(id=seq_request.id)).route_override is None

    assert post_form(client, f"/htmx/status/seq_request/{seq_request.id}/route", {"route": "nope"}, token=insider_token).status_code == 400


def test_statechart_json(client: TestClient, session: SyncSession, user, insider_token: str, user_token: str):
    seq_request = create_seq_request(session, user)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.commit()

    response = get(client, f"/htmx/status/seq_request/{seq_request.id}/statechart", insider_token)
    assert response.status_code == 200
    data = response.json()
    cards = {c["id"]: c for c in data["cards"]}
    assert cards["SUBMITTED"]["current"] and not cards["SUBMITTED"]["side"]
    assert cards["REJECTED"]["side"]
    transitions = {t["id"]: t for t in data["transitions"]}
    accept = transitions["SUBMITTED->ACCEPTED"]
    assert accept["fromCurrent"] and accept["state"] == "available"
    assert accept["actions"][0]["id"] == "request.accept"
    assert any("Libraries: SUBMITTED → ACCEPTED" in e for e in accept["actions"][0]["effects"])
    assert transitions["DRAFT->SUBMITTED"]["state"] == "inactive"

    assert get(client, f"/htmx/status/seq_request/{seq_request.id}/statechart", user_token).status_code == 403


def test_tab_mounts_the_chart(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = create_seq_request(session, user)
    session.commit()
    text = get(client, f"/htmx/status/seq_request/{seq_request.id}", insider_token, htmx=True).text
    assert f'id="status-chart-seq_request-{seq_request.id}"' in text
    assert "js/status-graph.js" in text
    assert f"/htmx/status/seq_request/{seq_request.id}/statechart" in text


@pytest.mark.parametrize("entity, child", [("project", "Requests"), ("lab_prep", "Libraries"), ("experiment", "Pools")])
def test_contents_get_a_kanban_instead_of_the_chart(client: TestClient, session: SyncSession, user, insider, insider_token: str, entity: str, child: str):
    _, _, obj_id = _objects(session, insider)[entity]
    text = get(client, f"/htmx/status/{entity}/{obj_id}", insider_token, htmx=True).text
    assert f'aria-label="{child.lower()} by status"' in text
    assert "status-chart-" not in text


def test_lab_prep_kanban_cards_link_to_libraries(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = create_seq_request(session, user)
    lab_prep = create_lab_prep(session, user)
    library = create_library(session, user, seq_request)
    library.lab_prep_id = lab_prep.id
    library.status = C.LibraryStatus.PREPARING
    session.commit()
    text = get(client, f"/htmx/status/lab_prep/{lab_prep.id}", insider_token, htmx=True).text
    assert 'data-status="PREPARING"' in text
    assert f'href="/libraries/{library.id}"' in text or f"/libraries/{library.id}\"" in text
    assert f"BSR_{seq_request.id:04d}" in text


def test_tab_is_read_only(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    lab_prep = create_lab_prep(session, user)
    session.commit()
    for entity, obj_id in (("seq_request", seq_request.id), ("lab_prep", lab_prep.id)):
        text = get(client, f"/htmx/status/{entity}/{obj_id}", insider_token, htmx=True).text
        posts = re.findall(r'hx-post="([^"]*)"', text)
        assert set(posts) <= {f"http://testserver/htmx/status/seq_request/{seq_request.id}/route"}  # only the route menu
        assert text.count("<button") == len(posts)
    # the route sits behind the cog: its name as a tooltip, the routes in its dropdown
    text = get(client, f"/htmx/status/seq_request/{seq_request.id}", insider_token, htmx=True).text
    assert re.search(r'class="status-route-toggle[^"]*" data-bs-toggle="dropdown"[^>]*title="Route: Raw samples, in-house library prep \(inferred\)"', text)
    menu = text[text.index('class="dropdown-menu'):]
    assert menu.count('name="route"') == len(transition_routes.ROUTES) + 1  # every route and "infer"
