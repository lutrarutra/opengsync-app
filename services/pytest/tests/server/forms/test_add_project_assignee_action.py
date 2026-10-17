"""AddProjectAssigneeAction: render, permissions, validation, and assignment.

Access control:
- **Init()** requires the project to exist (404 if not).
- **GET (Begin)** requires ``require_insider`` — only staff can view.
- **POST (Submit)** requires ``require_insider``.
- The assigned user must be an insider and not already an assignee.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_project, create_user
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

PREFIX = "/htmx/projects"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _render_path(project_id: int) -> str:
    return f"{PREFIX}/add-assignee/{project_id}"


def _submit_path(project_id: int) -> str:
    return f"{PREFIX}/add-assignee/{project_id}"


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "user_id": "",
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _commit(session: SyncSession) -> None:
    session.commit()


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_get_allows_insider(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    project = create_project(session, user)
    _commit(session)

    response = get(client, _render_path(project.id), insider_token)

    assert response.status_code == 200
    assert 'name="user_id"' in response.text
    assert 'name="csrf_token"' in response.text


def test_render_get_denies_client(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    _commit(session)

    response = get(client, _render_path(project.id), user_token)

    assert response.status_code == 403


def test_render_get_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    assert get(client, _render_path(999999), insider_token).status_code == 404


def test_render_get_autofills_current_user(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """If the current user is not already an assignee, their ID is pre-filled."""
    project = create_project(session, user)
    _commit(session)

    response = get(client, _render_path(project.id), insider_token)

    assert response.status_code == 200
    assert str(insider.id) in response.text


# ── Submit (POST) ────────────────────────────────────────────────────────────


def test_submit_requires_insider(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    user_token: str,
):
    """Send a valid user_id to pass validation; the insider check should then deny."""
    project = create_project(session, user)
    _commit(session)

    response = post_form(
        client,
        _submit_path(project.id),
        _payload(user_id=insider.id),
        token=user_token,
    )

    assert response.status_code == 403


def test_submit_adds_assignee(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    project = create_project(session, user)
    _commit(session)

    response = post_form(
        client,
        _submit_path(project.id),
        _payload(user_id=insider.id),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert_flash(response, "Assignee added successfully.", category="success")

    session.expire_all()
    updated = session.get_one(Q.project.select(id=project.id))
    assert insider in updated.assignees


def test_submit_rejects_non_insider_assignee(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    """Assigning a CLIENT user should fail because they are not an insider."""
    project = create_project(session, user)
    _commit(session)

    response = post_form(
        client,
        _submit_path(project.id),
        _payload(user_id=user.id),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert "Only insider users can be assigned to projects" in response.text


def test_submit_rejects_duplicate_assignee(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """Adding the same insider twice should fail."""
    project = create_project(session, user)
    project.assignees.append(insider)
    session.save(project)
    _commit(session)

    response = post_form(
        client,
        _submit_path(project.id),
        _payload(user_id=insider.id),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert "already an assignee" in response.text


def test_submit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    project = create_project(session, user)
    _commit(session)

    response = post_form_csrf_mismatch(
        client,
        _submit_path(project.id),
        _payload(user_id=insider.id),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")


def test_submit_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    response = post_form(
        client,
        _submit_path(999999),
        _payload(user_id=1),
        token=insider_token,
    )

    assert response.status_code == 404