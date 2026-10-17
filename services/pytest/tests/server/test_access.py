"""Role gating and resource-level AccessLevel enforcement over HTTP."""

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q, categories as C

from ..db.create_units import (
    create_project, create_seq_request, create_sample, create_library,
    create_pool, create_group,
)
from ._http import auth, get, delete, post_form, flush_redis


def _allowed(response) -> None:
    assert response.status_code not in (303, 401, 403)


def _anon_login_redirect(response) -> None:
    assert response.status_code == 303
    assert "/auth/login" in response.headers.get("location", "")


def _commit(session: SyncSession) -> None:
    session.commit()


def _affiliate(session: SyncSession, user, group, type: C.AffiliationType):
    session.save(Q.affiliation.create(user=user, group=group, type=type), flush=True)


# --- anonymous: listing and resource pages require login ---

@pytest.mark.parametrize("path", [  # type: ignore[attr-defined]
    "/",
    "/projects/",
    "/seq_requests/",
    "/samples/",
    "/libraries/",
    "/pools/",
    "/groups/",
    "/users/",
    "/kits",
    "/experiments/",
    "/lab_preps/",
    "/protocols/",
    "/seq_runs/",
    "/share_tokens/",
    "/admin/",
    "/sequencers/",
    "/browser/",
    "/design/",
])
def test_anon_listing_pages_redirect_to_login(client: TestClient, path: str):
    _anon_login_redirect(get(client, path))


@pytest.mark.parametrize("path", [  # type: ignore[attr-defined]
    "/projects/1",
    "/seq_requests/1",
    "/samples/1",
    "/libraries/1",
    "/pools/1",
    "/groups/1",
    "/users/1",
    "/kits/1",
    "/experiments/1",
    "/lab_preps/1",
    "/protocols/1",
    "/seq_runs/1",
    "/admin/",
])
def test_anon_resource_pages_redirect_to_login(client: TestClient, path: str):
    _anon_login_redirect(get(client, path))


@pytest.mark.parametrize("path", [  # type: ignore[attr-defined]
    "/htmx/comments/comment",
    "/htmx/groups/1/add-user",
    "/htmx/workflows/lane-qc/begin",
])
def test_anon_htmx_get_redirects_to_login(client: TestClient, path: str):
    _anon_login_redirect(get(client, path))


def test_anon_cannot_post_comment(client: TestClient):
    _anon_login_redirect(post_form(
        client, "/htmx/comments/comment",
        {"comment": "nope"},
        params={"seq_request_id": 1},
    ))


def test_anon_cannot_add_user_to_group(client: TestClient):
    _anon_login_redirect(post_form(
        client, "/htmx/groups/1/add-user",
        {"email": "a@b.com", "affiliation_type": str(C.AffiliationType.MEMBER.id)},
    ))


# --- client (regular user) listing ---

def test_user_can_access_projects(client: TestClient, user_token: str):
    _allowed(client.get("/projects/", headers=auth(user_token), follow_redirects=False))


def test_user_cannot_access_users_page(client: TestClient, user_token: str):
    response = client.get("/users/", headers=auth(user_token), follow_redirects=False)
    assert response.status_code == 403


def test_user_cannot_access_experiments(client: TestClient, user_token: str):
    response = client.get("/experiments/", headers=auth(user_token), follow_redirects=False)
    assert response.status_code == 403


def test_user_cannot_access_admin(client: TestClient, user_token: str):
    # Intended: admin only. require_admin uses `role < ADMIN` (CLIENT id=4), so a
    # 200 here is a product bug, not a bad test.
    response = client.get("/admin/", headers=auth(user_token), follow_redirects=False)
    assert response.status_code == 403


# --- insider listing ---

def test_insider_can_access_projects(client: TestClient, insider_token: str):
    _allowed(client.get("/projects/", headers=auth(insider_token), follow_redirects=False))


def test_insider_can_access_users_page(client: TestClient, insider_token: str):
    _allowed(client.get("/users/", headers=auth(insider_token), follow_redirects=False))


def test_insider_can_access_experiments(client: TestClient, insider_token: str):
    _allowed(client.get("/experiments/", headers=auth(insider_token), follow_redirects=False))


def test_insider_cannot_access_admin(client: TestClient, insider_token: str):
    response = client.get("/admin/", headers=auth(insider_token), follow_redirects=False)
    assert response.status_code == 403


# --- admin listing ---

def test_admin_can_access_projects(client: TestClient, admin_token: str):
    _allowed(client.get("/projects/", headers=auth(admin_token), follow_redirects=False))


def test_admin_can_access_users_page(client: TestClient, admin_token: str):
    _allowed(client.get("/users/", headers=auth(admin_token), follow_redirects=False))


def test_admin_can_access_experiments(client: TestClient, admin_token: str):
    _allowed(client.get("/experiments/", headers=auth(admin_token), follow_redirects=False))


def test_admin_can_access_admin_page(client: TestClient, admin_token: str):
    _allowed(client.get("/admin/", headers=auth(admin_token), follow_redirects=False))


# --- resource pages: project ---

def test_draft_project_owner_ok_stranger_403(
    client: TestClient, session: SyncSession, user, user_token, user_2_token,
):
    project = create_project(session, user)
    _commit(session)

    assert get(client, f"/projects/{project.id}", user_token).status_code == 200
    assert get(client, f"/projects/{project.id}", user_2_token).status_code == 403


def test_processing_project_owner_ok_stranger_403(
    client: TestClient, session: SyncSession, user, user_token, user_2_token,
):
    project = create_project(session, user)
    project.status = C.ProjectStatus.PROCESSING
    session.save(project)
    _commit(session)
    flush_redis(client)

    assert get(client, f"/projects/{project.id}", user_token).status_code == 200
    assert get(client, f"/projects/{project.id}", user_2_token).status_code == 403


def test_draft_project_group_member_ok(
    client: TestClient, session: SyncSession, user, user_2, user_token, user_2_token,
):
    group = create_group(session)
    _affiliate(session, user_2, group, C.AffiliationType.MEMBER)
    project = session.save(Q.project.create(
        title="grouped", description="d", owner_id=user.id, group_id=group.id,
    ), flush=True)
    _commit(session)

    assert get(client, f"/projects/{project.id}", user_2_token).status_code == 200
    assert get(client, f"/projects/{project.id}", user_token).status_code == 200


def test_draft_project_owner_can_delete_processing_cannot(
    client: TestClient, session: SyncSession, user, user_token,
):
    draft = create_project(session, user)
    processing = create_project(session, user)
    processing.status = C.ProjectStatus.PROCESSING
    session.save(processing)
    _commit(session)
    flush_redis(client)

    _allowed(delete(client, f"/htmx/projects/{draft.id}/delete", user_token))
    assert delete(client, f"/htmx/projects/{processing.id}/delete", user_token).status_code == 403


def test_project_insider_and_admin_ok(
    client: TestClient, session: SyncSession, user, insider_token, admin_token,
):
    project = create_project(session, user)
    _commit(session)

    assert get(client, f"/projects/{project.id}", insider_token).status_code == 200
    assert get(client, f"/projects/{project.id}", admin_token).status_code == 200


def test_project_missing_is_404(client: TestClient, user_token: str):
    assert get(client, "/projects/999999", user_token).status_code == 404


# --- seq request page ---

def test_seq_request_page_owner_ok(
    client: TestClient, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user)
    _commit(session)
    assert get(client, f"/seq_requests/{seq_request.id}", user_token).status_code == 200


def test_seq_request_page_stranger_403(
    client: TestClient, session: SyncSession, user, user_2_token,
):
    seq_request = create_seq_request(session, user)
    _commit(session)
    assert get(client, f"/seq_requests/{seq_request.id}", user_2_token).status_code == 403


def test_submitted_seq_request_requestor_ok(
    client: TestClient, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.save(seq_request)
    _commit(session)
    flush_redis(client)
    assert get(client, f"/seq_requests/{seq_request.id}", user_token).status_code == 200


def test_draft_seq_request_group_member_ok(
    client: TestClient, session: SyncSession, user, user_2, user_2_token,
):
    group = create_group(session)
    _affiliate(session, user_2, group, C.AffiliationType.MEMBER)
    seq_request = create_seq_request(session, user)
    seq_request.group = group
    session.save(seq_request)
    _commit(session)

    assert get(client, f"/seq_requests/{seq_request.id}", user_2_token).status_code == 200


def test_draft_seq_request_owner_can_delete_submitted_cannot(
    client: TestClient, session: SyncSession, user, user_token,
):
    draft = create_seq_request(session, user)
    submitted = create_seq_request(session, user)
    submitted.status = C.SeqRequestStatus.SUBMITTED
    session.save(submitted)
    _commit(session)
    flush_redis(client)

    _allowed(delete(client, f"/htmx/seq_requests/{draft.id}/delete", user_token))
    assert delete(client, f"/htmx/seq_requests/{submitted.id}/delete", user_token).status_code == 403


def test_seq_request_missing_is_404(client: TestClient, user_token: str):
    assert get(client, "/seq_requests/999999", user_token).status_code == 404


# --- sample / library / pool ---

def test_sample_follows_project_owner_ok_stranger_403(
    client: TestClient, session: SyncSession, user, user_token, user_2_token,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    _commit(session)

    assert get(client, f"/samples/{sample.id}", user_token).status_code == 200
    assert get(client, f"/samples/{sample.id}", user_2_token).status_code == 403


def test_sample_follows_project_group_member_ok(
    client: TestClient, session: SyncSession, user, user_2, user_2_token,
):
    group = create_group(session)
    _affiliate(session, user_2, group, C.AffiliationType.MEMBER)
    project = session.save(Q.project.create(
        title="grouped", description="d", owner_id=user.id, group_id=group.id,
    ), flush=True)
    sample = create_sample(session, user, project)
    _commit(session)

    assert get(client, f"/samples/{sample.id}", user_2_token).status_code == 200


def test_draft_sample_owner_can_delete_processing_project_cannot(
    client: TestClient, session: SyncSession, user, user_token,
):
    draft_project = create_project(session, user)
    draft_sample = create_sample(session, user, draft_project)
    processing_project = create_project(session, user)
    processing_sample = create_sample(session, user, processing_project)
    processing_project.status = C.ProjectStatus.PROCESSING
    session.save(processing_project)
    _commit(session)
    flush_redis(client)

    _allowed(delete(client, f"/htmx/samples/{draft_sample.id}/delete", user_token))
    assert delete(client, f"/htmx/samples/{processing_sample.id}/delete", user_token).status_code == 403


def test_library_follows_seq_request_owner_ok_library_owner_ignored(
    client: TestClient, session: SyncSession, user, user_2, user_token, user_2_token,
):
    seq_request = create_seq_request(session, user)
    library = create_library(session, user_2, seq_request)
    _commit(session)

    assert get(client, f"/libraries/{library.id}", user_token).status_code == 200
    assert get(client, f"/libraries/{library.id}", user_2_token).status_code == 403


def test_library_follows_seq_request_group_member_ok(
    client: TestClient, session: SyncSession, user, user_2, user_2_token,
):
    group = create_group(session)
    _affiliate(session, user_2, group, C.AffiliationType.MEMBER)
    seq_request = create_seq_request(session, user)
    seq_request.group = group
    session.save(seq_request)
    library = create_library(session, user, seq_request)
    _commit(session)

    assert get(client, f"/libraries/{library.id}", user_2_token).status_code == 200


def test_library_follows_submitted_seq_request_requestor_ok_stranger_403(
    client: TestClient, session: SyncSession, user, user_token, user_2_token,
):
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.save(seq_request)
    _commit(session)
    flush_redis(client)

    assert get(client, f"/libraries/{library.id}", user_token).status_code == 200
    assert get(client, f"/libraries/{library.id}", user_2_token).status_code == 403


def test_pool_requestor_ok_stranger_403(
    client: TestClient, session: SyncSession, user, user_token, user_2_token,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    assert get(client, f"/pools/{pool.id}", user_token).status_code == 200
    assert get(client, f"/pools/{pool.id}", user_2_token).status_code == 403


def test_sample_missing_is_404(client: TestClient, user_token: str):
    assert get(client, "/samples/999999", user_token).status_code == 404


def test_library_missing_is_404(client: TestClient, user_token: str):
    assert get(client, "/libraries/999999", user_token).status_code == 404


def test_pool_missing_is_404(client: TestClient, user_token: str):
    assert get(client, "/pools/999999", user_token).status_code == 404


def test_library_insider_ok(
    client: TestClient, session: SyncSession, user, insider_token,
):
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    _commit(session)
    assert get(client, f"/libraries/{library.id}", insider_token).status_code == 200


# --- group ---

def test_group_member_ok_outsider_403(
    client: TestClient, session: SyncSession, user, user_2, user_token, user_2_token,
):
    group = create_group(session)
    session.save(Q.affiliation.create(user=user, group=group, type=C.AffiliationType.MEMBER), flush=True)
    _commit(session)

    assert get(client, f"/groups/{group.id}", user_token).status_code == 200
    assert get(client, f"/groups/{group.id}", user_2_token).status_code == 403


def test_group_missing_is_404(client: TestClient, user_token: str):
    assert get(client, "/groups/999999", user_token).status_code == 404


# --- user ---

def test_user_self_ok_other_client_403(
    client: TestClient, user, user_2, user_token, user_2_token,
):
    assert get(client, f"/users/{user.id}", user_token).status_code == 200
    assert get(client, f"/users/{user.id}", user_2_token).status_code == 403


def test_user_insider_can_view_other(client: TestClient, user, insider_token):
    assert get(client, f"/users/{user.id}", insider_token).status_code == 200


def test_user_missing_is_404(client: TestClient, user_token: str):
    assert get(client, "/users/999999", user_token).status_code == 404
