"""MergeUsersAction: admin-only, two steps (preview, then merge) on the users list page.

- Preview shows what moves and blocking conflicts, and changes nothing;
- Merge moves everything to the destination user, deletes the source user and redirects to the destination;
- rejected before anything changes: missing or unknown user, same user twice, merging away one's own
  account, both users owning a project with the same title (also when the preview step is skipped);
- cached logins, users and API tokens of either user are dropped, so the merge takes effect immediately;
- a failure during the merge leaves both users untouched.

DB-level behaviour is covered in ``db/test_user_merge.py``; admin-only access in ``server/test_action_access.py``.
"""

import importlib
from html import unescape

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_project
from .._http import (
    assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch,
)

PATH = "/htmx/users/merge-users"
PREVIEW_PATH = f"{PATH}/preview"
merge_module = importlib.import_module("server.forms.actions.MergeUsersAction")


def _payload(dst: models.User | None, src: models.User | None) -> dict[str, str]:
    return {
        "user_dst": str(dst.id) if dst else "",
        "user_src": str(src.id) if src else "",
    }


def _exists(session: SyncSession, user_id: int) -> bool:
    session.expire_all()
    return session.get(models.User, user_id) is not None


@pytest.fixture
def users(session: SyncSession, user: models.User, user_2: models.User) -> tuple[models.User, models.User]:
    """(destination, source): both can log in, so their sessions can be checked after the merge."""
    return user, user_2


# ── Render ──────────────────────────────────────────────────────────────────


def test_render(client: TestClient, admin_token: str):
    response = get(client, PATH, admin_token)

    assert response.status_code == 200
    assert 'name="user_dst"' in response.text
    assert 'name="user_src"' in response.text
    assert PREVIEW_PATH in response.text


@pytest.mark.parametrize("token_fixture, shown", [("admin_token", True), ("insider_token", False)])
def test_users_page_button_only_for_admins(client: TestClient, request, token_fixture: str, shown: bool):
    response = get(client, "/users/", request.getfixturevalue(token_fixture))

    assert response.status_code == 200
    assert ("merge-users-btn" in response.text) is shown


# ── Preview ─────────────────────────────────────────────────────────────────


def test_preview_lists_what_moves_and_changes_nothing(
    client: TestClient, session: SyncSession, admin_token: str, users,
):
    dst, src = users
    project = create_project(session, src)
    session.commit()

    response = post_form(client, PREVIEW_PATH, _payload(dst, src), token=admin_token)

    assert response.status_code == 200
    assert "merge-users-preview" in response.text
    assert "Projects" in response.text
    assert f'name="user_dst" value="{dst.id}"' in response.text
    assert f'name="user_src" value="{src.id}"' in response.text
    assert _exists(session, src.id)
    assert session.get(models.Project, project.id).owner_id == src.id


def test_preview_shows_conflicts_and_disables_merge(
    client: TestClient, session: SyncSession, admin_token: str, users,
):
    dst, src = users
    for owner in (dst, src):
        create_project(session, owner).title = "same title"
    session.commit()

    response = post_form(client, PREVIEW_PATH, _payload(dst, src), token=admin_token)

    assert response.status_code == 200
    assert "merge-users-conflicts" in response.text
    assert "'same title'" in unescape(response.text)
    submit_button = response.text.split('id="submit-merge-users-btn"')[1].split(">")[0]
    assert "disabled" in submit_button


# ── Merge ───────────────────────────────────────────────────────────────────


def test_merge_moves_everything_and_deletes_source(
    client: TestClient, session: SyncSession, admin_token: str, users,
):
    dst, src = users
    dst_id, src_id = dst.id, src.id
    project = create_project(session, src)
    session.commit()

    response = post_form(client, PATH, _payload(dst, src), token=admin_token)

    assert_htmx_redirect(response, f"/users/{dst_id}")
    assert_flash(response, "Users merged successfully!", category="success")
    assert not _exists(session, src_id)
    assert session.get(models.Project, project.id).owner_id == dst_id


def test_source_login_stops_working(client: TestClient, session: SyncSession, admin_token: str, users, user_2_token: str):
    dst, src = users
    assert get(client, "/htmx/users/search", user_2_token).status_code == 200  # caches the source user

    response = post_form(client, PATH, _payload(dst, src), token=admin_token)
    assert response.status_code == 204

    assert get(client, "/htmx/users/search", user_2_token).status_code != 200


def test_destination_gets_role_immediately(
    client: TestClient, session: SyncSession, admin_token: str, users, user_token: str,
):
    dst, src = users
    src.role = C.UserRole.TECHNICIAN
    session.commit()
    assert get(client, "/htmx/projects/merge-projects", user_token).status_code == 403  # caches the destination user

    response = post_form(client, PATH, _payload(dst, src), token=admin_token)
    assert response.status_code == 204

    assert get(client, "/htmx/projects/merge-projects", user_token).status_code == 200


def test_source_api_token_now_belongs_to_destination(
    client: TestClient, session: SyncSession, admin_token: str, users,
):
    dst, src = users
    token = session.save(Q.api_token.create(owner=src, time_valid_min=60), flush=True)
    session.commit()
    headers = {"X-API-Token": token.plaintext}
    assert client.get("/api/validate-api_token", headers=headers).json()["owner_id"] == src.id  # caches the owner

    response = post_form(client, PATH, _payload(dst, src), token=admin_token)
    assert response.status_code == 204

    assert client.get("/api/validate-api_token", headers=headers).json()["owner_id"] == dst.id


# ── Rejections ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", [PREVIEW_PATH, PATH])
@pytest.mark.parametrize("missing", ["user_dst", "user_src"])
def test_missing_user_is_rejected(client: TestClient, session: SyncSession, admin_token: str, users, path, missing):
    dst, src = users
    payload = _payload(dst, src)
    payload[missing] = ""

    response = post_form(client, path, payload, token=admin_token)

    assert_form_invalid(response)
    assert _exists(session, src.id)


@pytest.mark.parametrize("path", [PREVIEW_PATH, PATH])
def test_unknown_user_is_rejected(client: TestClient, session: SyncSession, admin_token: str, users, path):
    dst, src = users
    payload = _payload(dst, src)
    payload["user_dst"] = "999999"

    response = post_form(client, path, payload, token=admin_token)

    assert_form_invalid(response, "Selected user not found.")
    assert _exists(session, src.id)


@pytest.mark.parametrize("path", [PREVIEW_PATH, PATH])
def test_same_user_is_rejected(client: TestClient, session: SyncSession, admin_token: str, users, path):
    dst, _ = users

    response = post_form(client, path, _payload(dst, dst), token=admin_token)

    assert_form_invalid(response, "Source and destination users cannot be the same.")
    assert _exists(session, dst.id)


@pytest.mark.parametrize("path", [PREVIEW_PATH, PATH])
def test_own_account_cannot_be_merged_away(
    client: TestClient, session: SyncSession, admin: models.User, admin_token: str, users, path,
):
    dst, _ = users

    response = post_form(client, path, _payload(dst, admin), token=admin_token)

    assert_form_invalid(response, "You cannot merge away your own account.")
    assert _exists(session, admin.id)


def test_title_clash_is_rejected_without_preview(
    client: TestClient, session: SyncSession, admin_token: str, users,
):
    dst, src = users
    for owner in (dst, src):
        create_project(session, owner).title = "same title"
    session.commit()

    response = post_form(client, PATH, _payload(dst, src), token=admin_token)

    assert_form_invalid(response, "'same title'")
    assert _exists(session, src.id)


def test_csrf_mismatch_changes_nothing(client: TestClient, session: SyncSession, admin_token: str, users):
    dst, src = users

    response = post_form_csrf_mismatch(client, PATH, _payload(dst, src), token=admin_token)

    assert_form_invalid(response)
    assert _exists(session, src.id)


# ── Rollback ────────────────────────────────────────────────────────────────


def test_failure_during_merge_rolls_everything_back(
    client: TestClient, session: SyncSession, admin_token: str, users, monkeypatch,
):
    dst, src = users
    project = create_project(session, src)
    session.commit()

    real_merge = merge_module.actions.merge_users

    def merge_then_fail(*args, **kwargs):
        real_merge(*args, **kwargs)
        raise RuntimeError("simulated failure after merging")

    monkeypatch.setattr(merge_module.actions, "merge_users", merge_then_fail)
    lenient = TestClient(client.app, raise_server_exceptions=False)

    response = post_form(lenient, PATH, _payload(dst, src), token=admin_token)

    assert response.status_code == 500
    assert _exists(session, src.id)
    assert session.get(models.Project, project.id).owner_id == src.id
