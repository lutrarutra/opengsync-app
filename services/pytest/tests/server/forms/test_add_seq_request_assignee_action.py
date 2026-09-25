"""AddSeqRequestAssigneeAction and the dashboard self-assign route.

Two separate ways to add an assignee:
- **AddSeqRequestAssigneeAction** (``/<seq_request_id>/add-assignee``): the form
  on the request page, where an insider can assign any insider via the
  searchable ``user_id`` field.
- **self_assign_seq_request** (``/<seq_request_id>/self-assign``): the quick
  "Assign yourself" dashboard button. It only ever assigns the current user.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q

from ...db.create_units import create_seq_request
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

PREFIX = "/htmx/seq_requests"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _form_path(seq_request_id: int) -> str:
    return f"{PREFIX}/{seq_request_id}/add-assignee"


def _self_assign_path(seq_request_id: int) -> str:
    return f"{PREFIX}/{seq_request_id}/self-assign"


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "user_id": "",
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _commit(session: SyncSession) -> None:
    session.commit()


# ── Form: render (GET) ──────────────────────────────────────────────────────


def test_render_get_allows_insider(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = get(client, _form_path(seq_request.id), insider_token)

    assert response.status_code == 200
    assert 'name="user_id"' in response.text
    assert 'name="csrf_token"' in response.text


def test_render_get_denies_client(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = get(client, _form_path(seq_request.id), user_token)

    assert response.status_code == 403


def test_render_get_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    assert get(client, _form_path(999999), insider_token).status_code == 404


def test_render_get_autofills_current_user(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """If the current user is not already an assignee, their ID is pre-filled."""
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = get(client, _form_path(seq_request.id), insider_token)

    assert response.status_code == 200
    assert str(insider.id) in response.text


# ── Form: submit (POST) ─────────────────────────────────────────────────────


def test_submit_requires_insider(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    user_token: str,
):
    """Send a valid user_id to pass validation; the insider check should then deny."""
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form(
        client,
        _form_path(seq_request.id),
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
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form(
        client,
        _form_path(seq_request.id),
        _payload(user_id=insider.id),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert_flash(response, "Assignee added successfully.", category="success")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert insider in updated.assignees


def test_submit_assigns_other_user_not_current_user(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    admin,
    insider_token: str,
):
    """Regression: the form must assign the selected user, not whoever submits it."""
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form(
        client,
        _form_path(seq_request.id),
        _payload(user_id=admin.id),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert admin in updated.assignees
    assert insider not in updated.assignees


def test_submit_rejects_non_insider_assignee(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    """Assigning a CLIENT user should fail because they are not an insider."""
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form(
        client,
        _form_path(seq_request.id),
        _payload(user_id=user.id),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert "Only insider users can be assigned to requests" in response.text


def test_submit_rejects_duplicate_assignee(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """Adding the same insider twice should fail."""
    seq_request = create_seq_request(session, user)
    seq_request.assignees.append(insider)
    session.save(seq_request)
    _commit(session)

    response = post_form(
        client,
        _form_path(seq_request.id),
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
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form_csrf_mismatch(
        client,
        _form_path(seq_request.id),
        _payload(user_id=insider.id),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert insider not in updated.assignees


def test_submit_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    response = post_form(
        client,
        _form_path(999999),
        _payload(user_id=1),
        token=insider_token,
    )

    assert response.status_code == 404


# ── Dashboard self-assign (raw route) ────────────────────────────────────────


def test_self_assign_requires_insider(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form(client, _self_assign_path(seq_request.id), {}, token=user_token)

    assert response.status_code == 403


def test_self_assign_adds_current_user(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form(client, _self_assign_path(seq_request.id), {}, token=insider_token)

    assert_htmx_redirect(response, "/")
    assert_flash(response, "Assignee Added!", category="success")

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert insider in updated.assignees


def test_self_assign_ignores_assignee_id_param(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    admin,
    insider_token: str,
):
    """The quick route cannot be used to assign anyone other than the current user."""
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form(
        client,
        f"{_self_assign_path(seq_request.id)}?assignee_id={admin.id}",
        {},
        token=insider_token,
    )

    assert response.status_code == 204

    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    assert insider in updated.assignees
    assert admin not in updated.assignees


def test_self_assign_rejects_duplicate(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    seq_request = create_seq_request(session, user)
    seq_request.assignees.append(insider)
    session.save(seq_request)
    _commit(session)

    response = post_form(client, _self_assign_path(seq_request.id), {}, token=insider_token)

    assert response.status_code == 400


def test_self_assign_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    response = post_form(client, _self_assign_path(999999), {}, token=insider_token)

    assert response.status_code == 404
