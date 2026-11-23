"""Mark data shared: records a data release that happened outside the app (backfill).

Same statuses as 'Share data' (libraries SEQUENCED -> SHARED, project DELIVERED once all libraries are
sequenced, delivery emails DISPATCHED), but no email is sent and the share link is left alone.
Admins and bioinformaticians with WRITE access only, as 'Share data'.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, actions, models, queries as Q, categories as C

from ..db.create_units import create_library, create_project, create_sample, create_seq_request
from ._http import assert_flash, assert_htmx_redirect, get, post_form


def _mark_shared(client: TestClient, project: models.Project, token: str):
    return post_form(client, f"/htmx/projects/{project.id}/mark-shared", {}, token=token, htmx=True)


def _project_with_libraries(
    session: SyncSession, user: models.User, *library_statuses: C.LibraryStatus,
) -> tuple[models.Project, models.SeqRequest, list[models.Library]]:
    project = create_project(session, user)
    project.status = C.ProjectStatus.SEQUENCED
    session.save(project)
    seq_request = create_seq_request(session, user)
    libraries = []
    for status in library_statuses:
        sample = create_sample(session, user, project)
        library = create_library(session, user, seq_request)
        actions.link_sample_library(session, sample.id, library.id)
        library.status = status
        session.save(library, flush=True)
        libraries.append(library)
    return project, seq_request, libraries


def _status(session: SyncSession, obj):
    session.expire_all()
    return session.get(type(obj), obj.id).status


def test_marks_libraries_shared_and_project_delivered(
    client: TestClient, session: SyncSession, user, bioinformatician_token,
):
    project, _, libraries = _project_with_libraries(
        session, user, C.LibraryStatus.SEQUENCED, C.LibraryStatus.FAILED,
    )
    session.commit()

    response = _mark_shared(client, project, bioinformatician_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert_flash(response, "No email was sent", "success")
    assert _status(session, libraries[0]) == C.LibraryStatus.SHARED
    assert _status(session, libraries[1]) == C.LibraryStatus.FAILED
    assert _status(session, project) == C.ProjectStatus.DELIVERED


def test_project_stays_when_libraries_are_not_all_sequenced(
    client: TestClient, session: SyncSession, user, bioinformatician_token,
):
    project, _, libraries = _project_with_libraries(
        session, user, C.LibraryStatus.SEQUENCED, C.LibraryStatus.POOLED,
    )
    session.commit()

    _mark_shared(client, project, bioinformatician_token)

    assert _status(session, libraries[0]) == C.LibraryStatus.SHARED
    assert _status(session, libraries[1]) == C.LibraryStatus.POOLED
    assert _status(session, project) == C.ProjectStatus.SEQUENCED


def test_dispatches_all_delivery_emails_without_sending_or_new_share_link(
    client: TestClient, session: SyncSession, user, bioinformatician, bioinformatician_token, monkeypatch,
):
    project, seq_request, _ = _project_with_libraries(session, user, C.LibraryStatus.SEQUENCED)
    seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(email="a@example.com"))
    seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(email="b@example.com"))
    session.save(seq_request)
    share_token = session.save(Q.share_token.create(owner=bioinformatician, time_valid_min=60, paths=["results"]), flush=True)
    project.share_token = share_token
    session.save(project)
    session.commit()
    share_uuid = share_token.uuid

    sent = []
    mailer = client.app.state.mailer  # type: ignore[attr-defined]
    monkeypatch.setattr(mailer, "send_share_project_data", lambda **kwargs: sent.append(kwargs))

    _mark_shared(client, project, bioinformatician_token)

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert {link.status for link in updated.delivery_email_links} == {C.DeliveryStatus.DISPATCHED}
    reloaded = session.get_one(Q.project.select(id=project.id))
    assert reloaded.share_token is not None and reloaded.share_token.uuid == share_uuid
    assert not reloaded.share_token._expired
    assert sent == []


def test_without_sequenced_libraries_is_noop(
    client: TestClient, session: SyncSession, user, bioinformatician_token,
):
    project, _, libraries = _project_with_libraries(session, user, C.LibraryStatus.POOLED)
    session.commit()

    response = _mark_shared(client, project, bioinformatician_token)

    assert_flash(response, "no sequenced libraries", "warning")
    assert _status(session, libraries[0]) == C.LibraryStatus.POOLED
    assert _status(session, project) == C.ProjectStatus.SEQUENCED


def test_owner_and_insider_cannot_mark_shared(
    client: TestClient, session: SyncSession, user, user_token, insider_token,
):
    project, _, libraries = _project_with_libraries(session, user, C.LibraryStatus.SEQUENCED)
    session.commit()

    assert _mark_shared(client, project, user_token).status_code == 403
    assert _mark_shared(client, project, insider_token).status_code == 403
    assert _status(session, libraries[0]) == C.LibraryStatus.SEQUENCED


def test_project_page_shows_action_to_data_assigners_only(
    client: TestClient, session: SyncSession, user, user_token, insider_token, bioinformatician_token,
):
    project, _, _ = _project_with_libraries(session, user, C.LibraryStatus.SEQUENCED)
    session.commit()

    url = f"/htmx/projects/{project.id}/mark-shared"
    assert url in get(client, f"/projects/{project.id}", bioinformatician_token).text
    assert url not in get(client, f"/projects/{project.id}", insider_token).text
    assert url not in get(client, f"/projects/{project.id}", user_token).text


def test_project_page_hides_action_without_sequenced_libraries(
    client: TestClient, session: SyncSession, user, bioinformatician_token,
):
    project, _, _ = _project_with_libraries(session, user, C.LibraryStatus.SHARED)
    session.commit()

    assert f"/htmx/projects/{project.id}/mark-shared" not in get(client, f"/projects/{project.id}", bioinformatician_token).text
