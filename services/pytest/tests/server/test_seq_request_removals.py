"""Removing libraries and samples from a seq request.

- Sequenced libraries can only be removed by admins.
- Samples can only be removed from a submitted request by admins, because that
  deletes every library of the sample in the request, sequenced ones included.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C
from opengsync_db.core import actions

from ..db.create_units import create_library, create_project, create_sample, create_seq_request
from ._http import delete

PREFIX = "/htmx/seq_requests"


def _submitted_request(session: SyncSession, owner: models.User) -> models.SeqRequest:
    seq_request = create_seq_request(session, owner)
    seq_request.status = C.SeqRequestStatus.ACCEPTED
    session.save(seq_request)
    return seq_request


def _library(session: SyncSession, owner: models.User, seq_request: models.SeqRequest, status: C.LibraryStatus) -> models.Library:
    library = create_library(session, owner, seq_request)
    library.status = status
    session.save(library)
    session.commit()
    return library


def _library_exists(session: SyncSession, library_id: int) -> bool:
    session.expire_all()
    return session.first(Q.library.select(id=library_id)) is not None


def test_insider_cannot_remove_sequenced_library(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = _submitted_request(session, user)
    library = _library(session, user, seq_request, C.LibraryStatus.SEQUENCED)

    response = delete(client, f"{PREFIX}/{seq_request.id}/remove-library/{library.id}", insider_token, htmx=True)

    assert response.status_code == 403
    assert _library_exists(session, library.id)


def test_insider_can_remove_unsequenced_library_from_submitted_request(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    seq_request = _submitted_request(session, user)
    library = _library(session, user, seq_request, C.LibraryStatus.ACCEPTED)

    response = delete(client, f"{PREFIX}/{seq_request.id}/remove-library/{library.id}", insider_token, htmx=True)

    assert response.status_code < 400, response.text
    assert not _library_exists(session, library.id)


def test_admin_can_remove_sequenced_library(client: TestClient, session: SyncSession, user, admin_token: str):
    seq_request = _submitted_request(session, user)
    library = _library(session, user, seq_request, C.LibraryStatus.SEQUENCED)

    response = delete(client, f"{PREFIX}/{seq_request.id}/remove-library/{library.id}", admin_token, htmx=True)

    assert response.status_code < 400, response.text
    assert not _library_exists(session, library.id)


def _sample_with_library(session: SyncSession, owner: models.User, seq_request: models.SeqRequest) -> tuple[models.Sample, models.Library]:
    sample = create_sample(session, owner, create_project(session, owner))
    library = create_library(session, owner, seq_request)
    actions.link_sample_library(session, sample.id, library.id)
    session.commit()
    return sample, library


def test_insider_cannot_remove_sample_from_submitted_request(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    seq_request = _submitted_request(session, user)
    sample, library = _sample_with_library(session, user, seq_request)

    response = delete(client, f"{PREFIX}/{seq_request.id}/remove-sample/{sample.id}", insider_token, htmx=True)

    assert response.status_code == 403
    assert _library_exists(session, library.id)


def test_admin_can_remove_sample_from_submitted_request(
    client: TestClient, session: SyncSession, user, admin_token: str,
):
    seq_request = _submitted_request(session, user)
    sample, library = _sample_with_library(session, user, seq_request)

    response = delete(client, f"{PREFIX}/{seq_request.id}/remove-sample/{sample.id}", admin_token, htmx=True)

    assert response.status_code < 400, response.text
    assert not _library_exists(session, library.id)


def test_owner_can_remove_sample_from_draft_request(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = create_seq_request(session, user)
    sample, library = _sample_with_library(session, user, seq_request)

    response = delete(client, f"{PREFIX}/{seq_request.id}/remove-sample/{sample.id}", user_token, htmx=True)

    assert response.status_code < 400, response.text
    assert not _library_exists(session, library.id)
