"""LibraryPrepAction: render, permissions, field validation, and persistence.

Access control:
- **Init()** requires the lab prep to exist (404 if not).
- **GET (Begin)** requires ``require_insider`` — only staff can view.
- **POST (Submit)** requires ``require_insider``.
- Adds selected libraries to a lab prep.
"""

import json

import sqlalchemy as sa

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_seq_request, create_library
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    delete,
    get,
    post_form,
    post_form_csrf_mismatch,
)

PREFIX = "/htmx/actions/library-prep"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _render_path(lab_prep_id: int) -> str:
    return f"{PREFIX}/{lab_prep_id}"


def _submit_path(lab_prep_id: int) -> str:
    return f"{PREFIX}/{lab_prep_id}"


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "selected_library_ids": json.dumps([]),
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _create_lab_prep(
    session: SyncSession,
    user: models.User,
    *,
    checklist_type: C.LabChecklistType = C.LabChecklistType.CUSTOM,
    service_type: C.ServiceType = C.ServiceType.CUSTOM,
) -> models.LabPrep:
    """Factory helper: create a lab prep fixture in the DB."""
    prep = session.save(
        Q.lab_prep.create(
            name="test-prep",
            creator=user,
            number=1,
            checklist_type=checklist_type,
            service_type=service_type,
        ),
        flush=True,
    )
    session.commit()
    return prep


def _lab_prep_with_accepted_libraries(
    session: SyncSession,
    user: models.User,
    *,
    num_libraries: int = 2,
) -> tuple[models.LabPrep, list[models.Library]]:
    """Create a lab prep and *n* accepted libraries (not yet added to the prep)."""
    lab_prep = _create_lab_prep(session, user)
    seq_request = create_seq_request(session, user)
    libraries: list[models.Library] = []
    for _ in range(num_libraries):
        lib = create_library(session, user, seq_request)
        lib.status = C.LibraryStatus.ACCEPTED
        libraries.append(lib)
    session.commit()
    return lab_prep, libraries


def _commit(session: SyncSession) -> None:
    session.commit()


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_get_allows_insider(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    lab_prep, _ = _lab_prep_with_accepted_libraries(session, user)

    response = get(client, _render_path(lab_prep.id), insider_token)

    assert response.status_code == 200
    assert 'name="selected_library_ids"' in response.text
    assert 'name="csrf_token"' in response.text


def test_render_get_denies_client(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    lab_prep, _ = _lab_prep_with_accepted_libraries(session, user)

    response = get(client, _render_path(lab_prep.id), user_token)

    assert response.status_code == 403


def test_render_get_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    assert get(client, _render_path(999999), insider_token).status_code == 404


# ── Submit (POST) ────────────────────────────────────────────────────────────


def test_submit_requires_insider(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    lab_prep, libraries = _lab_prep_with_accepted_libraries(session, user)

    response = post_form(
        client,
        _submit_path(lab_prep.id),
        _payload(selected_library_ids=json.dumps([libraries[0].id])),
        token=user_token,
    )

    assert response.status_code == 403


def test_submit_adds_libraries_to_prep(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    lab_prep, libraries = _lab_prep_with_accepted_libraries(session, user)
    assert len(lab_prep.libraries) == 0

    response = post_form(
        client,
        _submit_path(lab_prep.id),
        _payload(selected_library_ids=json.dumps([libraries[0].id, libraries[1].id])),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/lab_preps/{lab_prep.id}")
    assert_flash(response, "Libraries added to prep!", category="success")

    session.expire_all()
    updated = session.get_one(Q.lab_prep.select(id=lab_prep.id))
    assert len(updated.libraries) == 2
    assert libraries[0] in updated.libraries
    assert libraries[1] in updated.libraries


def test_submit_rejects_empty_selection(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    lab_prep, _ = _lab_prep_with_accepted_libraries(session, user)

    response = post_form(
        client,
        _submit_path(lab_prep.id),
        _payload(selected_library_ids=json.dumps([])),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert "Please select at least one item." in response.text


def test_submit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    lab_prep, libraries = _lab_prep_with_accepted_libraries(session, user)

    response = post_form_csrf_mismatch(
        client,
        _submit_path(lab_prep.id),
        _payload(selected_library_ids=json.dumps([libraries[0].id])),
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
        _payload(selected_library_ids=json.dumps([1])),
        token=insider_token,
    )

    assert response.status_code == 404

# ── Status (PREPARING restored, regression from d9685235) ───────────────────


def test_submit_sets_libraries_below_preparing_to_preparing(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    lab_prep, libraries = _lab_prep_with_accepted_libraries(session, user, num_libraries=3)
    libraries[1].status = C.LibraryStatus.SUBMITTED
    libraries[2].status = C.LibraryStatus.STORED
    session.commit()

    response = post_form(
        client,
        _submit_path(lab_prep.id),
        _payload(selected_library_ids=json.dumps([lib.id for lib in libraries])),
        token=insider_token,
    )
    assert_htmx_redirect(response, f"/lab_preps/{lab_prep.id}")

    session.expire_all()
    statuses = [session.get_one(Q.library.select(id=lib.id)).status for lib in libraries]
    assert statuses == [C.LibraryStatus.PREPARING, C.LibraryStatus.PREPARING, C.LibraryStatus.STORED]

    [run] = session.execute(
        sa.select(models.OperationRun).where(models.OperationRun.operation == "prep.add_libraries")
    ).scalars().all()
    assert run.actor_id == insider.id
    assert len(run.changes) == 2


def test_remove_library_reverts_preparing(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    lab_prep, libraries = _lab_prep_with_accepted_libraries(session, user)
    libraries[0].status = C.LibraryStatus.PREPARING
    libraries[0].lab_prep_id = lab_prep.id
    libraries[1].status = C.LibraryStatus.POOLED
    libraries[1].lab_prep_id = lab_prep.id
    session.commit()

    for library in libraries:
        response = delete(client, f"/htmx/lab_preps/{lab_prep.id}/remove-library?library_id={library.id}", insider_token, htmx=True)
        assert response.status_code in (200, 204), response.text

    session.expire_all()
    first, second = (session.get_one(Q.library.select(id=lib.id)) for lib in libraries)
    assert (first.lab_prep_id, first.status) == (None, C.LibraryStatus.ACCEPTED)
    assert (second.lab_prep_id, second.status) == (None, C.LibraryStatus.POOLED)


def test_remove_library_of_another_prep_is_404(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    lab_prep, libraries = _lab_prep_with_accepted_libraries(session, user, num_libraries=1)
    other = _create_lab_prep(session, user)
    libraries[0].lab_prep_id = other.id
    session.commit()

    response = delete(client, f"/htmx/lab_preps/{lab_prep.id}/remove-library?library_id={libraries[0].id}", insider_token, htmx=True)
    assert response.status_code == 404
    session.expire_all()
    assert session.get_one(Q.library.select(id=libraries[0].id)).lab_prep_id == other.id
