"""ShareProjectDataAction: render, permissions, validation, and share-token creation.

Access control:
- **Init()** requires the project to exist (404 if not).
- **GET (Begin)** requires WRITE on the project (owner of a DRAFT project, or insider).
- **POST (Submit)** requires WRITE on the project.
- Non-insiders cannot send to custom emails or create links longer than the default validity.
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, actions, queries as Q, categories as C

from server.core import config
from server.forms.actions.ShareProjectDataAction import DEFAULT_TIME_VALID_MIN, TIME_VALID_CHOICES

from ...db.create_units import create_library, create_project, create_sample, create_seq_request
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

RECIPIENT = "recipient@example.com"
CUSTOM_EMAIL = "custom@example.com"


def _path(project_id: int) -> str:
    return f"{PREFIX}/{project_id}/share-data"


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, object] = {
        "recipients": json.dumps([RECIPIENT]),
        "anonymous_send": "false",
        "send_to_owner": "false",
        "time_valid_min": DEFAULT_TIME_VALID_MIN,
        "internal_share": "false",
        "custom_email": "",
        "mark_project_delivered": "true",
    }
    data.update(overrides)
    return {key: str(value) for key, value in data.items() if value is not None}


def _add_data_path(session: SyncSession, project: models.Project, path: str) -> models.DataPath:
    return session.save(Q.data_path.create(path=path, type=C.DataPathType.DIRECTORY, project=project), flush=True)


def _shareable_project(session: SyncSession, owner: models.User) -> models.Project:
    project = create_project(session, owner)
    _add_data_path(session, project, "results")
    session.commit()
    return project


def _reload_project(session: SyncSession, project_id: int) -> models.Project:
    session.expire_all()
    return session.get_one(Q.project.select(id=project_id))


def _input_tag(html: str, name: str) -> str:
    match = re.search(rf'<input[^>]*name="{name}"[^>]*>', html)
    assert match is not None, f"input {name!r} not rendered"
    return match.group(0)


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_get_allows_draft_owner(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """Owner of a DRAFT project has WRITE access."""
    project = _shareable_project(session, user)

    response = get(client, _path(project.id), user_token)

    assert response.status_code == 200
    assert 'name="custom_email"' in response.text
    assert "results" in response.text
    assert _path(project.id) in response.text


def test_render_get_custom_email_read_only_for_client(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = _shareable_project(session, user)

    response = get(client, _path(project.id), user_token)

    assert response.status_code == 200
    assert "readonly" in _input_tag(response.text, "custom_email")


def test_render_get_custom_email_editable_for_insider(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    project = _shareable_project(session, user)

    response = get(client, _path(project.id), insider_token)

    assert response.status_code == 200
    assert "readonly" not in _input_tag(response.text, "custom_email")


def test_render_get_denies_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    project = _shareable_project(session, user)

    assert get(client, _path(project.id), user_2_token).status_code == 403


def test_render_get_denies_owner_of_non_draft_project(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """Owners only have READ once the project leaves DRAFT."""
    project = _shareable_project(session, user)
    project.status = C.ProjectStatus.DELIVERED
    session.save(project)
    session.commit()

    assert get(client, _path(project.id), user_token).status_code == 403


def test_render_get_unknown_is_404(
    client: TestClient,
    user_token: str,
):
    assert get(client, _path(999999), user_token).status_code == 404


# ── Submit (POST) ────────────────────────────────────────────────────────────


def test_submit_creates_share_token(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    project = create_project(session, user)
    _add_data_path(session, project, "results")
    _add_data_path(session, project, "results/sub")
    session.commit()

    response = post_form(client, _path(project.id), _payload(), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert_flash(response, "Data Share Email Sent!", category="success")

    updated = _reload_project(session, project.id)
    assert updated.status == C.ProjectStatus.DELIVERED
    share_token = updated.share_token
    assert share_token is not None
    assert share_token.owner_id == insider.id
    assert share_token.time_valid_min == DEFAULT_TIME_VALID_MIN
    # Subpaths of already-shared directories are dropped.
    assert [p.path for p in share_token.paths] == ["results"]


def test_submit_as_draft_owner(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """Non-insiders with WRITE can share to the project owner."""
    project = _shareable_project(session, user)

    response = post_form(
        client, _path(project.id),
        _payload(recipients=json.dumps([]), send_to_owner="true"),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/projects/{project.id}")
    updated = _reload_project(session, project.id)
    assert updated.share_token is not None
    assert updated.share_token.owner_id == user.id


def test_submit_without_marking_delivered_keeps_status(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    project = _shareable_project(session, user)

    response = post_form(
        client, _path(project.id), _payload(mark_project_delivered="false"), token=insider_token,
    )

    assert_htmx_redirect(response, f"/projects/{project.id}")
    updated = _reload_project(session, project.id)
    assert updated.status == C.ProjectStatus.DRAFT
    assert updated.share_token is not None


def test_submit_expires_previous_share_token(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    project = _shareable_project(session, user)
    old_token = session.save(Q.share_token.create(
        owner=insider, time_valid_min=DEFAULT_TIME_VALID_MIN, paths=["results"],
    ), flush=True)
    project.share_token = old_token
    session.save(project)
    session.commit()
    old_uuid = old_token.uuid

    response = post_form(client, _path(project.id), _payload(), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    updated = _reload_project(session, project.id)
    assert updated.share_token is not None
    assert updated.share_token.uuid != old_uuid
    assert session.get_one(Q.share_token.select(uuid=old_uuid))._expired


def test_submit_marks_matching_delivery_links_dispatched(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    project = _shareable_project(session, user)
    seq_request = create_seq_request(session, user)
    sample = create_sample(session, user, project)
    library = create_library(session, user, seq_request)
    actions.link_sample_library(session, sample.id, library.id)
    seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(email=RECIPIENT))
    seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(email="other@example.com"))
    session.save(seq_request)
    session.commit()

    response = post_form(client, _path(project.id), _payload(), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    session.expire_all()
    updated = session.get_one(Q.seq_request.select(id=seq_request.id))
    statuses = {link.email: link.status for link in updated.delivery_email_links}
    assert statuses[RECIPIENT] == C.DeliveryStatus.DISPATCHED
    assert statuses["other@example.com"] == C.DeliveryStatus.PENDING


def test_submit_sends_email_in_prod(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
    fake_mailer,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "prod")
    project = _shareable_project(session, user)

    response = post_form(
        client, _path(project.id),
        _payload(send_to_owner="true", custom_email=CUSTOM_EMAIL),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/projects/{project.id}")
    [sent] = [mail for mail in fake_mailer.sent if mail["method"] == "send_share_project_data"]
    assert sorted(sent["kwargs"]["recipients"]) == sorted([RECIPIENT, user.email, CUSTOM_EMAIL])


def test_submit_does_not_send_email_outside_prod(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
    fake_mailer,
):
    project = _shareable_project(session, user)

    response = post_form(client, _path(project.id), _payload(), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert fake_mailer.sent == []


def test_submit_requires_recipients(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    project = _shareable_project(session, user)

    response = post_form(
        client, _path(project.id), _payload(recipients=json.dumps([])), token=insider_token,
    )

    assert_form_invalid(response, "No recipients selected.")
    assert _reload_project(session, project.id).share_token is None


@pytest.mark.parametrize("recipients", ["not-json", json.dumps({"email": RECIPIENT})])
def test_submit_rejects_invalid_recipients_payload(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
    recipients: str,
):
    project = _shareable_project(session, user)

    response = post_form(
        client, _path(project.id), _payload(recipients=recipients), token=insider_token,
    )

    assert_form_invalid(response, "Invalid recipients payload.")


def test_submit_requires_data_paths(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    project = create_project(session, user)
    session.commit()

    response = post_form(client, _path(project.id), _payload(), token=insider_token)

    assert_form_invalid(response, "No data paths available to share.")
    assert _reload_project(session, project.id).share_token is None


def test_submit_client_cannot_send_to_custom_email(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = _shareable_project(session, user)

    response = post_form(
        client, _path(project.id), _payload(custom_email=CUSTOM_EMAIL), token=user_token,
    )

    assert_form_invalid(response, "You don't have permissions to send to custom email addresses.")
    assert _reload_project(session, project.id).share_token is None


def test_submit_client_cannot_exceed_default_validity(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = _shareable_project(session, user)

    response = post_form(
        client, _path(project.id), _payload(time_valid_min=TIME_VALID_CHOICES[-1][0]), token=user_token,
    )

    assert_form_invalid(response, "You don't have permissions to create a link that lasts more than")
    assert _reload_project(session, project.id).share_token is None


def test_submit_insider_can_exceed_default_validity(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    project = _shareable_project(session, user)
    time_valid_min = TIME_VALID_CHOICES[-1][0]

    response = post_form(
        client, _path(project.id), _payload(time_valid_min=time_valid_min), token=insider_token,
    )

    assert_htmx_redirect(response, f"/projects/{project.id}")
    share_token = _reload_project(session, project.id).share_token
    assert share_token is not None
    assert share_token.time_valid_min == time_valid_min


def test_submit_requires_write(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    project = _shareable_project(session, user)

    response = post_form(client, _path(project.id), _payload(), token=user_2_token)

    assert response.status_code == 403
    assert _reload_project(session, project.id).share_token is None


def test_submit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    project = _shareable_project(session, user)

    response = post_form_csrf_mismatch(client, _path(project.id), _payload(), token=insider_token)

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")


def test_submit_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    response = post_form(client, _path(999999), _payload(), token=insider_token)

    assert response.status_code == 404
