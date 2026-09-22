"""ProjectForm: create/edit, permissions, uniqueness, and relationship validation.

Note: the ``group`` field exists on the form but is not rendered by
``forms/project.html`` (same as the legacy Flask template), so group validation
is only reachable through a direct POST.  Those tests therefore assert rejection
and non-persistence instead of rendered error text.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_group, create_project
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

CREATE = "/htmx/projects/create"
EDIT = "/htmx/projects/{project_id}/edit"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _edit_path(project_id: int) -> str:
    return EDIT.format(project_id=project_id)


def _payload(title: str, **overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "title": title,
        "description": "A test project description",
        "status": str(C.ProjectStatus.DRAFT.id),
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _affiliate(session: SyncSession, user: models.User, group: models.Group) -> None:
    session.save(
        Q.affiliation.create(user=user, group=group, type=C.AffiliationType.MEMBER),
        flush=True,
    )
    session.commit()


def _project(session: SyncSession, title: str) -> models.Project | None:
    session.expire_all()
    return session.first(Q.project.select(title=title))


def _set_status(session: SyncSession, project: models.Project, status: C.ProjectStatus) -> None:
    project.status = status
    session.commit()


def test_create_form_get_prefills_owner(client: TestClient, user, user_token: str):
    response = get(client, CREATE, user_token)

    assert response.status_code == 200
    assert 'name="title"' in response.text
    assert 'name="owner"' in response.text
    assert 'name="csrf_token"' in response.text
    assert f'value="{user.id}"' in response.text


def test_create_form_requires_authentication(client: TestClient):
    response = get(client, CREATE)

    assert response.status_code == 303
    assert "/auth/login" in response.headers["location"]


def test_edit_form_get_renders_project_values(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    session.commit()

    response = get(client, _edit_path(project.id), user_token)

    assert response.status_code == 200
    assert project.title in response.text
    assert project.description in response.text


def test_edit_form_get_denied_for_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    project = create_project(session, user)
    session.commit()

    response = get(client, _edit_path(project.id), user_2_token)

    assert response.status_code == 403


def test_edit_form_get_denied_for_non_draft_project(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    _set_status(session, project, C.ProjectStatus.PROCESSING)

    response = get(client, _edit_path(project.id), user_token)

    assert response.status_code == 403


def test_edit_form_get_unknown_project_is_404(client: TestClient, user_token: str):
    assert get(client, _edit_path(999999), user_token).status_code == 404


def test_create_persists_project_and_redirects(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    title = "Newly Created Project"
    response = post_form(
        client,
        CREATE,
        _payload(title, owner=user.id),
        token=user_token,
    )

    assert_htmx_redirect(response, "/projects/")
    assert_flash(response, "Project Created!", category="success")

    project = _project(session, title)
    assert project is not None
    assert project.owner_id == user.id
    assert project.description == "A test project description"
    assert project.status == C.ProjectStatus.DRAFT
    assert project.identifier is None
    assert project.group_id is None


def test_create_requires_title(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form(client, CREATE, {"owner": str(user.id)}, token=user_token)

    assert_form_invalid(response)
    assert "Title is required" in response.text
    assert session.count(Q.project.select(owner_id=user.id)) == 0


def test_create_requires_owner(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form(client, CREATE, {"title": "Ownerless Project"}, token=user_token)

    assert_form_invalid(response)
    assert "Owner is required" in response.text
    assert _project(session, "Ownerless Project") is None


def test_create_title_max_length(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    title = "x" * (models.Project.title.type.length + 1)
    response = post_form(client, CREATE, _payload(title, owner=user.id), token=user_token)

    assert_form_invalid(response)
    assert _project(session, title) is None


def test_create_duplicate_title_for_owner_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    existing = create_project(session, user)
    session.commit()

    response = post_form(client, CREATE, _payload(existing.title, owner=user.id), token=user_token)

    assert_form_invalid(response, "You already have a project with this title.")
    assert session.count(Q.project.select(owner_id=user.id)) == 1


def test_create_duplicate_identifier_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    existing = create_project(session, user)
    existing.identifier = "BSA_0001"
    session.commit()

    response = post_form(
        client,
        CREATE,
        _payload("Identifier Clash", owner=user.id, identifier="BSA_0001"),
        token=insider_token,
    )

    assert_form_invalid(response, "This identifier is already taken.")
    assert _project(session, "Identifier Clash") is None


def test_create_client_cannot_set_identifier(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload("Client Identifier", owner=user.id, identifier="BSA_7777"),
        token=user_token,
    )

    assert_form_invalid(response, "Only insiders can set a project identifier.")
    assert _project(session, "Client Identifier") is None


def test_create_insider_can_set_identifier(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    title = "Insider Identifier"
    response = post_form(
        client,
        CREATE,
        _payload(title, owner=user.id, identifier="BSA_8888"),
        token=insider_token,
    )

    assert_htmx_redirect(response, "/projects/")
    project = _project(session, title)
    assert project is not None
    assert project.identifier == "BSA_8888"


def test_create_client_cannot_assign_another_owner(
    client: TestClient,
    session: SyncSession,
    user,
    user_2,
    user_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload("Stolen Ownership", owner=user_2.id),
        token=user_token,
    )

    assert_form_invalid(response, "You do not have permission to set this user as owner.")
    assert _project(session, "Stolen Ownership") is None


def test_create_insider_can_assign_another_owner(
    client: TestClient,
    session: SyncSession,
    user_2,
    insider_token: str,
):
    title = "Insider Assigned Owner"
    response = post_form(
        client,
        CREATE,
        _payload(title, owner=user_2.id),
        token=insider_token,
    )

    assert_htmx_redirect(response, "/projects/")
    project = _project(session, title)
    assert project is not None
    assert project.owner_id == user_2.id


def test_create_unknown_owner_rerenders(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload("Ghost Owner", owner=999999),
        token=insider_token,
    )

    assert_form_invalid(response, "Selected user does not exist.")
    assert _project(session, "Ghost Owner") is None


def test_create_client_cannot_set_non_draft_status(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload("Client Delivered", owner=user.id, status=C.ProjectStatus.DELIVERED.id),
        token=user_token,
    )

    assert_form_invalid(response, "status DRAFT")
    assert _project(session, "Client Delivered") is None


def test_create_insider_can_set_non_draft_status(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    title = "Insider Delivered"
    response = post_form(
        client,
        CREATE,
        _payload(title, owner=user.id, status=C.ProjectStatus.DELIVERED.id),
        token=insider_token,
    )

    assert_htmx_redirect(response, "/projects/")
    project = _project(session, title)
    assert project is not None
    assert project.status == C.ProjectStatus.DELIVERED


def test_create_with_group_persists_membership(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    group = create_group(session)
    _affiliate(session, user, group)

    title = "Grouped Project"
    response = post_form(
        client,
        CREATE,
        _payload(title, owner=user.id, group=group.id),
        token=user_token,
    )

    assert_htmx_redirect(response, "/projects/")
    project = _project(session, title)
    assert project is not None
    assert project.group_id == group.id


def test_create_group_requires_owner_membership(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    group = create_group(session)

    response = post_form(
        client,
        CREATE,
        _payload("Ungrouped Membership", owner=user.id, group=group.id),
        token=user_token,
    )

    assert_form_invalid(response)
    assert _project(session, "Ungrouped Membership") is None


def test_create_unknown_group_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload("Ghost Group", owner=user.id, group=999999),
        token=user_token,
    )

    assert_form_invalid(response)
    assert _project(session, "Ghost Group") is None


def test_create_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form_csrf_mismatch(
        client,
        CREATE,
        _payload("CSRF Project", owner=user.id),
        token=user_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert _project(session, "CSRF Project") is None


def test_edit_persists_title_and_description(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    session.commit()

    response = post_form(
        client,
        _edit_path(project.id),
        _payload("Updated Title", owner=user.id, description="Updated description"),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert_flash(response, "Project Updated!", category="success")

    session.expire_all()
    session.refresh(project)
    assert project.title == "Updated Title"
    assert project.description == "Updated description"


def test_edit_denied_for_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    project = create_project(session, user)
    session.commit()

    response = post_form(
        client,
        _edit_path(project.id),
        _payload("Hijacked Title", owner=user.id),
        token=user_2_token,
    )

    assert response.status_code == 403
    session.expire_all()
    session.refresh(project)
    assert project.title != "Hijacked Title"


def test_edit_denied_for_non_draft_project(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    _set_status(session, project, C.ProjectStatus.PROCESSING)

    response = post_form(
        client,
        _edit_path(project.id),
        _payload("Processing Edit", owner=user.id),
        token=user_token,
    )

    assert response.status_code == 403
    session.expire_all()
    session.refresh(project)
    assert project.title != "Processing Edit"


def test_edit_client_cannot_change_status(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    session.commit()

    response = post_form(
        client,
        _edit_path(project.id),
        _payload(project.title, owner=user.id, status=C.ProjectStatus.PROCESSING.id),
        token=user_token,
    )

    assert_form_invalid(response, "Only insiders can change project status.")
    session.expire_all()
    session.refresh(project)
    assert project.status == C.ProjectStatus.DRAFT


def test_edit_client_cannot_change_owner(
    client: TestClient,
    session: SyncSession,
    user,
    user_2,
    user_token: str,
):
    project = create_project(session, user)
    session.commit()

    response = post_form(
        client,
        _edit_path(project.id),
        _payload(project.title, owner=user_2.id),
        token=user_token,
    )

    assert_form_invalid(response, "Only insiders can change project owner.")
    session.expire_all()
    session.refresh(project)
    assert project.owner_id == user.id


def test_edit_client_cannot_set_identifier(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    session.commit()

    response = post_form(
        client,
        _edit_path(project.id),
        _payload(project.title, owner=user.id, identifier="BSA_6666"),
        token=user_token,
    )

    assert_form_invalid(response, "Only insiders can set a project identifier.")
    session.expire_all()
    session.refresh(project)
    assert project.identifier is None


def test_edit_insider_can_change_status_owner_and_identifier(
    client: TestClient,
    session: SyncSession,
    user,
    user_2,
    insider_token: str,
):
    project = create_project(session, user)
    session.commit()

    response = post_form(
        client,
        _edit_path(project.id),
        _payload(
            "Insider Edited",
            owner=user_2.id,
            status=C.ProjectStatus.PROCESSING.id,
            identifier="BSA_5555",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/projects/{project.id}")
    session.expire_all()
    session.refresh(project)
    assert project.title == "Insider Edited"
    assert project.owner_id == user_2.id
    assert project.status == C.ProjectStatus.PROCESSING
    assert project.identifier == "BSA_5555"


def test_edit_duplicate_title_for_owner_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    first = create_project(session, user)
    second = create_project(session, user)
    session.commit()

    response = post_form(
        client,
        _edit_path(first.id),
        _payload(second.title, owner=user.id),
        token=user_token,
    )

    assert_form_invalid(response, "You already have a project with this title.")
    session.expire_all()
    session.refresh(first)
    assert first.title != second.title


def test_edit_duplicate_identifier_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    other = create_project(session, user)
    other.identifier = "BSA_1111"
    project = create_project(session, user)
    session.commit()

    response = post_form(
        client,
        _edit_path(project.id),
        _payload(project.title, owner=user.id, identifier="BSA_1111"),
        token=insider_token,
    )

    assert_form_invalid(response, "This identifier is already taken.")
    session.expire_all()
    session.refresh(project)
    assert project.identifier is None


def test_edit_unknown_project_is_404(client: TestClient, user_token: str):
    response = post_form(
        client,
        _edit_path(999999),
        _payload("Missing Project", owner=1),
        token=user_token,
    )

    assert response.status_code == 404


def test_edit_group_requires_owner_membership(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    group = create_group(session)
    session.commit()

    response = post_form(
        client,
        _edit_path(project.id),
        _payload(project.title, owner=user.id, group=group.id),
        token=user_token,
    )

    assert_form_invalid(response)
    session.expire_all()
    session.refresh(project)
    assert project.group_id is None