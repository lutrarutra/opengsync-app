"""Archive / unarchive a project from the project page (insider only).

Only the project status changes; sample and library statuses are left untouched.
Unarchive derives the status from the libraries: none -> DRAFT,
all shared/failed/rejected/archived -> DELIVERED, otherwise PROCESSING.
"""

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, actions, models, categories as C

from ..db.create_units import create_library, create_project, create_sample, create_seq_request
from ._http import assert_flash, assert_htmx_redirect, get, post_form


def _archive(client: TestClient, project: models.Project, token: str):
    return post_form(client, f"/htmx/projects/{project.id}/archive", {}, token=token, htmx=True)


def _unarchive(client: TestClient, project: models.Project, token: str):
    return post_form(client, f"/htmx/projects/{project.id}/unarchive", {}, token=token, htmx=True)


def _project_with_library(
    session: SyncSession, user: models.User, library_status: C.LibraryStatus,
) -> tuple[models.Project, models.Sample, models.Library]:
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    library = create_library(session, user, create_seq_request(session, user))
    actions.link_sample_library(session, sample.id, library.id)
    library.status = library_status
    session.save(library, flush=True)
    return project, sample, library


def _status(session: SyncSession, obj):
    session.expire_all()
    return session.get(type(obj), obj.id).status


def test_insider_can_archive_project(client: TestClient, session: SyncSession, user, insider_token):
    project = create_project(session, user)
    project.status = C.ProjectStatus.DELIVERED
    session.save(project)
    session.commit()

    response = _archive(client, project, insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert_flash(response, "Archived project", "success")
    assert _status(session, project) == C.ProjectStatus.ARCHIVED


def test_archive_leaves_sample_and_library_statuses(client: TestClient, session: SyncSession, user, insider_token):
    project, sample, library = _project_with_library(session, user, C.LibraryStatus.SEQUENCED)
    project.status = C.ProjectStatus.SEQUENCED
    session.save(project)
    sample_status = sample.status
    session.commit()

    _archive(client, project, insider_token)

    assert _status(session, project) == C.ProjectStatus.ARCHIVED
    assert _status(session, library) == C.LibraryStatus.SEQUENCED
    assert _status(session, sample) == sample_status


@pytest.mark.parametrize("library_status, expected", [  # type: ignore[attr-defined]
    (None, C.ProjectStatus.DRAFT),
    (C.LibraryStatus.SHARED, C.ProjectStatus.DELIVERED),
    (C.LibraryStatus.FAILED, C.ProjectStatus.DELIVERED),
    (C.LibraryStatus.SEQUENCED, C.ProjectStatus.PROCESSING),
])
def test_unarchive_derives_status_from_libraries(
    client: TestClient, session: SyncSession, user, insider_token,
    library_status: C.LibraryStatus | None, expected: C.ProjectStatus,
):
    if library_status is None:
        project, library = create_project(session, user), None
    else:
        project, _, library = _project_with_library(session, user, library_status)
    project.status = C.ProjectStatus.ARCHIVED
    session.save(project)
    session.commit()

    response = _unarchive(client, project, insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert_flash(response, "Unarchived project", "success")
    assert _status(session, project) == expected
    if library is not None:
        assert _status(session, library) == library_status


def test_unarchive_non_archived_project_is_noop(client: TestClient, session: SyncSession, user, insider_token):
    project = create_project(session, user)
    project.status = C.ProjectStatus.SEQUENCED
    session.save(project)
    session.commit()

    response = _unarchive(client, project, insider_token)

    assert_flash(response, "is not archived", "warning")
    assert _status(session, project) == C.ProjectStatus.SEQUENCED


def test_owner_cannot_archive_or_unarchive(client: TestClient, session: SyncSession, user, user_token):
    project = create_project(session, user)
    session.commit()

    assert _archive(client, project, user_token).status_code == 403
    assert _status(session, project) == C.ProjectStatus.DRAFT

    project.status = C.ProjectStatus.ARCHIVED
    session.save(project)
    session.commit()

    assert _unarchive(client, project, user_token).status_code == 403
    assert _status(session, project) == C.ProjectStatus.ARCHIVED


def test_project_page_shows_archive_action_for_insider_only(
    client: TestClient, session: SyncSession, user, user_token, insider_token,
):
    project = create_project(session, user)
    session.commit()

    archive_url = f"/htmx/projects/{project.id}/archive"
    assert archive_url in get(client, f"/projects/{project.id}", insider_token).text
    assert archive_url not in get(client, f"/projects/{project.id}", user_token).text


def test_project_page_shows_unarchive_action_when_archived(
    client: TestClient, session: SyncSession, user, insider_token,
):
    project = create_project(session, user)
    project.status = C.ProjectStatus.ARCHIVED
    session.save(project)
    session.commit()

    text = get(client, f"/projects/{project.id}", insider_token).text
    assert f"/htmx/projects/{project.id}/unarchive" in text
    assert f"/htmx/projects/{project.id}/archive\"" not in text
