"""Status history through the web app: operation, kind, actor and comment of real requests.

Every server test already runs with app sessions in strict mode (conftest), so any status change
outside a declared operation fails there; these tests check what the history records.
"""
import sqlalchemy as sa
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C, actions

from ...db.create_units import create_seq_request, create_library, create_project, create_sample
from .._http import auth, get, post_form

LIBRARY_EDIT = "/htmx/libraries/{library_id}/edit"


def _runs(session: SyncSession, operation: str) -> list[models.OperationRun]:
    session.expire_all()
    return list(session.execute(
        sa.select(models.OperationRun).where(models.OperationRun.operation == operation).order_by(models.OperationRun.id)
    ).scalars())


def _library_payload(library: models.Library, **overrides: object) -> dict[str, str]:
    data = {
        "name": library.sample_name,
        "library_type": str(library.type.id),
        "genome": str(library.genome_ref.id),
        "status": str(library.status.id),
    }
    data.update({key: str(value) for key, value in overrides.items()})
    return data


def test_accept_records_the_insider(client: TestClient, session: SyncSession, user, insider, insider_token: str):
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    library.status = C.LibraryStatus.SUBMITTED
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.commit()

    response = post_form(
        client, f"/htmx/seq_requests/{seq_request.id}/process-request",
        {"response_type": str(C.RequestResponse.ACCEPTED.id), "notification_receiver": "n@example.com", "notification_comment": ""},
        token=insider_token,
    )
    assert response.status_code in (200, 204)

    [run] = _runs(session, "request.accept")
    assert run.kind == C.OperationKind.ACTION
    assert run.actor_id == insider.id
    assert (run.subject_type, run.subject_id) == ("seq_request", seq_request.id)
    assert {(c.entity_type, c.entity_id, c.from_status, c.to_status) for c in run.changes} == {
        ("seq_request", seq_request.id, C.SeqRequestStatus.SUBMITTED.id, C.SeqRequestStatus.ACCEPTED.id),
        ("library", library.id, C.LibraryStatus.SUBMITTED.id, C.LibraryStatus.ACCEPTED.id),
    }
    assert all(c.declared for c in run.changes)


def test_manual_status_edit_records_comment(client: TestClient, session: SyncSession, user, insider, insider_token: str):
    library = create_library(session, user, create_seq_request(session, user))
    session.commit()

    response = post_form(
        client, LIBRARY_EDIT.format(library_id=library.id),
        _library_payload(library, status=C.LibraryStatus.FAILED.id, status_comment="  degraded RNA  "),
        token=insider_token,
    )
    assert response.status_code in (200, 204)

    [run] = _runs(session, "manual.edit_library")
    assert run.kind == C.OperationKind.MANUAL
    assert (run.actor_id, run.comment) == (insider.id, "degraded RNA")
    assert [(c.from_status, c.to_status) for c in run.changes] == [(C.LibraryStatus.DRAFT.id, C.LibraryStatus.FAILED.id)]


def test_edit_without_status_change_records_nothing(client: TestClient, session: SyncSession, user, insider_token: str):
    library = create_library(session, user, create_seq_request(session, user))
    session.commit()

    response = post_form(
        client, LIBRARY_EDIT.format(library_id=library.id),
        _library_payload(library, name="Renamed_Library", status_comment="ignored without a status change"),
        token=insider_token,
    )
    assert response.status_code in (200, 204)
    assert _runs(session, "manual.edit_library") == []


def test_comment_field_only_when_status_is_editable(client: TestClient, session: SyncSession, user, user_token: str, insider_token: str):
    library = create_library(session, user, create_seq_request(session, user))
    session.commit()

    as_insider = get(client, LIBRARY_EDIT.format(library_id=library.id), insider_token, htmx=True)
    as_owner = get(client, LIBRARY_EDIT.format(library_id=library.id), user_token, htmx=True)
    assert 'name="status_comment"' in as_insider.text
    assert 'name="status_comment"' not in as_owner.text


def test_release_api_records_api_operation(client: TestClient, session: SyncSession, user, insider, insider_token: str):
    project = create_project(session, user)
    project.identifier = "P0001"
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    library.status = C.LibraryStatus.SEQUENCED
    sample = create_sample(session, user, project)
    actions.link_sample_library(session, sample.id, library.id)
    seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(email="customer@example.com"))
    session.save(Q.data_path.create(path="P0001/fastq", type=C.DataPathType.DIRECTORY, project=project))
    session.commit()

    response = client.post(
        "/api/shares/release-project_data",
        json={"project_id": project.id, "internal_access": False, "time_valid_min": 60, "recipients": ["customer@example.com"]},
        headers=auth(insider_token),
    )
    assert response.status_code == 200, response.text

    [run] = _runs(session, "api.release_project")
    assert run.kind == C.OperationKind.API
    assert run.actor_id == insider.id
    assert {(c.entity_type, c.to_status) for c in run.changes} == {
        ("project", C.ProjectStatus.DELIVERED.id),
        ("library", C.LibraryStatus.SHARED.id),
        ("seq_request_delivery_email_link", C.DeliveryStatus.DISPATCHED.id),
    }
    assert all(c.declared for c in run.changes)
