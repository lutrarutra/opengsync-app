"""ShareProjectDataAction: render, permissions, validation, and share-token creation.

Access control:
- **Init()** requires the project to exist (404 if not).
- **GET (Begin)** and **POST (Submit)** are insiders only: sharing releases the data (libraries SEQUENCED → SHARED,
  project DELIVERED), as the release API. Owners of a DRAFT project have WRITE but are still denied.
"""

import json
import re

import sqlalchemy as sa

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
    auth,
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


def test_render_get_as_insider(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician_token: str,
):
    project = _shareable_project(session, user)

    response = get(client, _path(project.id), bioinformatician_token)

    assert response.status_code == 200
    assert "readonly" not in _input_tag(response.text, "custom_email")
    assert "results" in response.text
    assert _path(project.id) in response.text


def test_render_get_denies_draft_owner(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """The owner of a DRAFT project has WRITE, but sharing is insiders only."""
    project = _shareable_project(session, user)

    assert get(client, _path(project.id), user_token).status_code == 403


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


@pytest.mark.parametrize("token_name, shown", [
    ("admin_token", True), ("bioinformatician_token", True), ("insider_token", False), ("user_token", False),
])
def test_share_data_button_only_for_data_assigners(
    request: pytest.FixtureRequest, client: TestClient, session: SyncSession, user, token_name: str, shown: bool,
):
    """Technicians and clients get a 403 from the action, so the project page doesn't offer it."""
    project = _shareable_project(session, user)

    page = get(client, f"/projects/{project.id}", request.getfixturevalue(token_name))
    assert page.status_code == 200
    assert (_path(project.id) in page.text) is shown


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
    bioinformatician,
    bioinformatician_token: str,
):
    project = create_project(session, user)
    _add_data_path(session, project, "results")
    _add_data_path(session, project, "results/sub")
    session.commit()

    response = post_form(client, _path(project.id), _payload(), token=bioinformatician_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert_flash(response, "Data Share Email Sent!", category="success")

    updated = _reload_project(session, project.id)
    assert updated.status == C.ProjectStatus.DELIVERED
    share_token = updated.share_token
    assert share_token is not None
    assert share_token.owner_id == bioinformatician.id
    assert share_token.time_valid_min == DEFAULT_TIME_VALID_MIN
    # Subpaths of already-shared directories are dropped.
    assert [p.path for p in share_token.paths] == ["results"]


def test_submit_denies_draft_owner(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """The owner of a DRAFT project has WRITE, but sharing is insiders only."""
    project = _shareable_project(session, user)

    response = post_form(
        client, _path(project.id),
        _payload(recipients=json.dumps([]), send_to_owner="true"),
        token=user_token,
    )

    assert response.status_code == 403
    updated = _reload_project(session, project.id)
    assert updated.share_token is None
    assert updated.status == C.ProjectStatus.DRAFT


def _project_with_library(session: SyncSession, owner: models.User, library_status: C.LibraryStatus) -> tuple[models.Project, models.Library]:
    project = _shareable_project(session, owner)
    seq_request = create_seq_request(session, owner)
    library = create_library(session, owner, seq_request)
    library.status = library_status
    sample = create_sample(session, owner, project)
    actions.link_sample_library(session, sample.id, library.id)
    session.commit()
    return project, library


def test_submit_without_marking_delivered_waits_for_sequenced_libraries(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician_token: str,
):
    """Unticked, as the release API: the project becomes DELIVERED only once all its libraries are sequenced."""
    project, library = _project_with_library(session, user, C.LibraryStatus.POOLED)

    response = post_form(
        client, _path(project.id), _payload(mark_project_delivered="false"), token=bioinformatician_token,
    )

    assert_htmx_redirect(response, f"/projects/{project.id}")
    updated = _reload_project(session, project.id)
    assert updated.status == C.ProjectStatus.DRAFT
    assert updated.share_token is not None
    assert session.get_one(Q.library.select(id=library.id)).status == C.LibraryStatus.POOLED


def test_submit_without_marking_delivered_delivers_sequenced_project(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician_token: str,
):
    project, library = _project_with_library(session, user, C.LibraryStatus.SEQUENCED)

    response = post_form(
        client, _path(project.id), _payload(mark_project_delivered="false"), token=bioinformatician_token,
    )

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert _reload_project(session, project.id).status == C.ProjectStatus.DELIVERED
    assert session.get_one(Q.library.select(id=library.id)).status == C.LibraryStatus.SHARED


def test_submit_sets_sequenced_libraries_shared(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician,
    bioinformatician_token: str,
):
    """As the release API: sequenced libraries become SHARED, so their requests can reach FINISHED."""
    project, library = _project_with_library(session, user, C.LibraryStatus.SEQUENCED)

    response = post_form(client, _path(project.id), _payload(), token=bioinformatician_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    session.expire_all()
    assert session.get_one(Q.library.select(id=library.id)).status == C.LibraryStatus.SHARED
    [run] = session.execute(
        sa.select(models.OperationRun).where(models.OperationRun.operation == "project.share_data")
    ).scalars().all()
    assert run.actor_id == bioinformatician.id
    assert {(c.entity_type, c.to_status) for c in run.changes} == {
        ("project", C.ProjectStatus.DELIVERED.id), ("library", C.LibraryStatus.SHARED.id),
    }


def test_submit_does_not_move_archived_project_back(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician_token: str,
):
    project = _shareable_project(session, user)
    project.status = C.ProjectStatus.ARCHIVED
    session.commit()

    response = post_form(client, _path(project.id), _payload(), token=bioinformatician_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert _reload_project(session, project.id).status == C.ProjectStatus.ARCHIVED


def test_share_and_release_api_change_the_same_statuses(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician_token: str,
):
    """The UI share and the release API run the same function, so they leave the same statuses."""
    results = []
    for via_api in (False, True):
        project, library = _project_with_library(session, user, C.LibraryStatus.SEQUENCED)
        project.identifier = f"P{project.id:04d}"
        session.commit()
        if via_api:
            response = client.post(
                "/api/shares/release-project_data",
                json={"project_id": project.id, "internal_access": False, "time_valid_min": 60, "recipients": [RECIPIENT]},
                headers=auth(bioinformatician_token),
            )
            assert response.status_code == 200, response.text
        else:
            post_form(client, _path(project.id), _payload(mark_project_delivered="false"), token=bioinformatician_token)
        session.expire_all()
        results.append((
            session.get_one(Q.project.select(id=project.id)).status,
            session.get_one(Q.library.select(id=library.id)).status,
        ))
    assert results[0] == results[1] == (C.ProjectStatus.DELIVERED, C.LibraryStatus.SHARED)


def test_submit_expires_previous_share_token(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician,
    bioinformatician_token: str,
):
    project = _shareable_project(session, user)
    old_token = session.save(Q.share_token.create(
        owner=bioinformatician, time_valid_min=DEFAULT_TIME_VALID_MIN, paths=["results"],
    ), flush=True)
    project.share_token = old_token
    session.save(project)
    session.commit()
    old_uuid = old_token.uuid

    response = post_form(client, _path(project.id), _payload(), token=bioinformatician_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    updated = _reload_project(session, project.id)
    assert updated.share_token is not None
    assert updated.share_token.uuid != old_uuid
    assert session.get_one(Q.share_token.select(uuid=old_uuid))._expired


def test_submit_marks_matching_delivery_links_dispatched(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician_token: str,
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

    response = post_form(client, _path(project.id), _payload(), token=bioinformatician_token)

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
    bioinformatician_token: str,
    fake_mailer,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "prod")
    project = _shareable_project(session, user)

    response = post_form(
        client, _path(project.id),
        _payload(send_to_owner="true", custom_email=CUSTOM_EMAIL),
        token=bioinformatician_token,
    )

    assert_htmx_redirect(response, f"/projects/{project.id}")
    [sent] = [mail for mail in fake_mailer.sent if mail["method"] == "send_share_project_data"]
    assert sorted(sent["kwargs"]["recipients"]) == sorted([RECIPIENT, user.email, CUSTOM_EMAIL])


def test_submit_does_not_send_email_outside_prod(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician_token: str,
    fake_mailer,
):
    project = _shareable_project(session, user)

    response = post_form(client, _path(project.id), _payload(), token=bioinformatician_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert fake_mailer.sent == []


def test_submit_requires_recipients(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician_token: str,
):
    project = _shareable_project(session, user)

    response = post_form(
        client, _path(project.id), _payload(recipients=json.dumps([])), token=bioinformatician_token,
    )

    assert_form_invalid(response, "No recipients selected.")
    assert _reload_project(session, project.id).share_token is None


@pytest.mark.parametrize("recipients", ["not-json", json.dumps({"email": RECIPIENT})])
def test_submit_rejects_invalid_recipients_payload(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician_token: str,
    recipients: str,
):
    project = _shareable_project(session, user)

    response = post_form(
        client, _path(project.id), _payload(recipients=recipients), token=bioinformatician_token,
    )

    assert_form_invalid(response, "Invalid recipients payload.")


def test_submit_requires_data_paths(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician_token: str,
):
    project = create_project(session, user)
    session.commit()

    response = post_form(client, _path(project.id), _payload(), token=bioinformatician_token)

    assert_form_invalid(response, "No data paths available to share.")
    assert _reload_project(session, project.id).share_token is None


def test_submit_insider_can_exceed_default_validity(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician_token: str,
):
    project = _shareable_project(session, user)
    time_valid_min = TIME_VALID_CHOICES[-1][0]

    response = post_form(
        client, _path(project.id), _payload(time_valid_min=time_valid_min), token=bioinformatician_token,
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
    bioinformatician_token: str,
):
    project = _shareable_project(session, user)

    response = post_form_csrf_mismatch(client, _path(project.id), _payload(), token=bioinformatician_token)

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")


def test_submit_unknown_is_404(
    client: TestClient,
    bioinformatician_token: str,
):
    response = post_form(client, _path(999999), _payload(), token=bioinformatician_token)

    assert response.status_code == 404


# ── Internal share and anonymous send ───────────────────────────────────────


@pytest.mark.parametrize("internal_share", [True, False])
@pytest.mark.parametrize("anonymous_send", [True, False])
def test_submit_passes_internal_share_and_anonymous_to_the_mailer(
    client: TestClient,
    session: SyncSession,
    user,
    bioinformatician_token: str,
    fake_mailer,
    monkeypatch: pytest.MonkeyPatch,
    internal_share: bool,
    anonymous_send: bool,
):
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "prod")
    project = _shareable_project(session, user)

    response = post_form(
        client, _path(project.id),
        _payload(internal_share=str(internal_share).lower(), anonymous_send=str(anonymous_send).lower()),
        token=bioinformatician_token,
    )

    assert_htmx_redirect(response, f"/projects/{project.id}")
    [sent] = [mail for mail in fake_mailer.sent if mail["method"] == "send_share_project_data"]
    assert sent["kwargs"]["internal_share"] is internal_share
    assert sent["kwargs"]["anonymous"] is anonymous_send


class _RenderedMail:
    """Records the mailer's template renders and the sent email instead of rendering/sending."""

    INTERNAL = "custom/share-internal-access.html"
    HEADER = "custom/share-project-data-email-header.html"
    BODY = "email/share-project-data.html"

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        from server.core import mailer as mailer_module

        self.renders: dict[str, dict] = {}
        self.sent: list[dict] = []
        for name in (self.INTERNAL, self.HEADER):
            (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / name).write_text("")
        monkeypatch.setattr(config.settings.app_config, "template_folder", str(tmp_path))
        monkeypatch.setattr(config.settings.app_config.personalization, "internal_share_template", self.INTERNAL)
        monkeypatch.setattr(config.settings.app_config, "share_path_mapping", {"results": "/mnt/share/results"})
        monkeypatch.setattr(mailer_module.templates, "render_template", self._render)
        monkeypatch.setattr(mailer_module.responses, "external_url_for", lambda *args, **kwargs: "https://example.com/share")
        monkeypatch.setattr(mailer_module.Mailer, "_get_email_style", lambda self: "")
        monkeypatch.setattr(mailer_module.Mailer, "_Mailer__send_email", lambda _, **kwargs: self.sent.append(kwargs))
        self.mailer = mailer_module.Mailer()

    def _render(self, name: str, **context) -> str:
        self.renders[name] = context
        return f"<{name}>"

    def send(self, session: SyncSession, project: models.Project, sender: models.User, internal_share: bool, anonymous: bool) -> None:
        share_token = session.save(Q.share_token.create(owner=sender, time_valid_min=60, paths=["results"]), flush=True)
        self.mailer.send_share_project_data(
            recipients=[RECIPIENT], share_token=share_token, current_user=sender, project=project,
            internal_share=internal_share, anonymous=anonymous,
        )


def test_internal_share_adds_mapped_internal_paths_to_the_email_header(
    session: SyncSession, user, bioinformatician, monkeypatch: pytest.MonkeyPatch, tmp_path,
):
    mail = _RenderedMail(monkeypatch, tmp_path)
    project = _shareable_project(session, user)

    mail.send(session, project, bioinformatician, internal_share=True, anonymous=False)

    assert mail.renders[mail.INTERNAL]["paths"] == ["/mnt/share/results"]
    assert mail.renders[mail.HEADER]["internal_share_content"] == f"<{mail.INTERNAL}>"
    assert [sent["recipients"] for sent in mail.sent] == [[RECIPIENT]]


def test_without_internal_share_the_internal_template_is_not_rendered(
    session: SyncSession, user, bioinformatician, monkeypatch: pytest.MonkeyPatch, tmp_path,
):
    mail = _RenderedMail(monkeypatch, tmp_path)
    project = _shareable_project(session, user)

    mail.send(session, project, bioinformatician, internal_share=False, anonymous=False)

    assert mail.INTERNAL not in mail.renders
    assert mail.renders[mail.HEADER]["internal_share_content"] == ""


@pytest.mark.parametrize("sender_fixture, anonymous, author_is_sender", [
    ("bioinformatician", False, True),
    ("bioinformatician", True, False),
    ("user", False, False),  # only insiders are named as the author
])
def test_anonymous_send_drops_the_author(
    request: pytest.FixtureRequest, session: SyncSession, user, monkeypatch: pytest.MonkeyPatch, tmp_path,
    sender_fixture: str, anonymous: bool, author_is_sender: bool,
):
    """As legacy: the author is passed to the email template (the default template does not show it)."""
    mail = _RenderedMail(monkeypatch, tmp_path)
    project = _shareable_project(session, user)
    sender = request.getfixturevalue(sender_fixture)

    mail.send(session, project, sender, internal_share=False, anonymous=anonymous)

    assert mail.renders[mail.BODY]["author"] is (sender if author_is_sender else None)


@pytest.mark.parametrize("minutes", ["999", "-1"])
def test_submit_rejects_validity_outside_the_choices(
    client: TestClient, session: SyncSession, user, bioinformatician_token: str, minutes: str,
):
    """As legacy's SelectField, also for insiders (who may pick longer periods)."""
    project = _shareable_project(session, user)

    response = post_form(client, _path(project.id), _payload(time_valid_min=minutes), token=bioinformatician_token)

    assert_form_invalid(response, "Not a valid choice")
    assert _reload_project(session, project.id).share_token is None
