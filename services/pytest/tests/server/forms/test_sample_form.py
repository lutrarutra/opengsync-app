"""SampleForm: edit rendering, name rules, status handling, and access control.

The form is edit-only — samples are created by the library-annotation and
sequencing-request flows, not here.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_group, create_project, create_sample
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

EDIT = "/htmx/samples/{sample_id}/edit"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"
DUPLICATE_MSG = "Project already has a sample with this name."


def _edit_path(sample_id: int) -> str:
    return EDIT.format(sample_id=sample_id)


def _payload(name: str, status: int | None = C.SampleStatus.STORED.id) -> dict[str, str]:
    data: dict[str, str] = {"name": name}
    if status is not None:
        data["status"] = str(status)
    return data


def _affiliate(session: SyncSession, user: models.User, group: models.Group) -> None:
    session.save(
        Q.affiliation.create(user=user, group=group, type=C.AffiliationType.MEMBER),
        flush=True,
    )
    session.commit()


def _reload(session: SyncSession, sample: models.Sample) -> models.Sample:
    session.expire_all()
    return session.get_one(Q.sample.select(id=sample.id))


def test_sample_form_exposes_only_edit_routes():
    from server.forms.models.SampleForm import SampleForm

    assert {(route.method, route.name) for route in SampleForm._routes} == {
        ("GET", "SampleForm.Edit"),
        ("POST", "SampleForm.Edit"),
    }


def test_edit_form_get_renders_sample(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    session.commit()

    response = get(client, _edit_path(sample.id), user_token)

    assert response.status_code == 200
    assert sample.name in response.text
    assert 'name="name"' in response.text
    assert 'name="status"' in response.text
    assert 'name="csrf_token"' in response.text


def test_edit_form_get_unknown_sample_is_404(client: TestClient, user_token: str):
    assert get(client, _edit_path(999999), user_token).status_code == 404


def test_edit_form_get_denied_for_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    session.commit()

    assert get(client, _edit_path(sample.id), user_2_token).status_code == 403


def test_edit_persists_name_and_status(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    session.commit()

    response = post_form(
        client,
        _edit_path(sample.id),
        _payload("Renamed_Sample", C.SampleStatus.STORED.id),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/samples/{sample.id}")
    assert_flash(response, "Changes saved!", category="success")

    updated = _reload(session, sample)
    assert updated.name == "Renamed_Sample"
    assert updated.status == C.SampleStatus.STORED


def test_edit_can_clear_status(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    sample.status = C.SampleStatus.STORED
    session.commit()

    response = post_form(
        client,
        _edit_path(sample.id),
        _payload("Statusless_Sample", status=None),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/samples/{sample.id}")
    assert _reload(session, sample).status is None


def test_edit_denied_for_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    session.commit()

    response = post_form(
        client,
        _edit_path(sample.id),
        _payload("Stolen_Sample"),
        token=user_2_token,
    )

    assert response.status_code == 403
    assert _reload(session, sample).name == sample.name


def test_edit_insider_can_rename(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    session.commit()

    response = post_form(
        client,
        _edit_path(sample.id),
        _payload("Insider_Renamed"),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/samples/{sample.id}")
    assert _reload(session, sample).name == "Insider_Renamed"


def test_edit_allowed_for_group_member(
    client: TestClient,
    session: SyncSession,
    user,
    user_2,
    user_2_token: str,
):
    project = create_project(session, user)
    group = create_group(session)
    project.group_id = group.id
    _affiliate(session, user_2, group)
    sample = create_sample(session, user, project)
    session.commit()

    response = post_form(
        client,
        _edit_path(sample.id),
        _payload("Group_Renamed"),
        token=user_2_token,
    )

    assert_htmx_redirect(response, f"/samples/{sample.id}")
    assert _reload(session, sample).name == "Group_Renamed"


def test_edit_allowed_on_non_draft_project(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """Legacy parity: sample editing requires READ, not WRITE."""
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    project.status = C.ProjectStatus.PROCESSING
    session.commit()

    response = post_form(
        client,
        _edit_path(sample.id),
        _payload("Still_Editable"),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/samples/{sample.id}")
    assert _reload(session, sample).name == "Still_Editable"


def test_edit_duplicate_name_within_project_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    first = create_sample(session, user, project)
    second = create_sample(session, user, project)
    first.name = "Sample_One"
    second.name = "Sample_Two"
    session.commit()

    response = post_form(
        client,
        _edit_path(first.id),
        _payload("Sample_Two"),
        token=user_token,
    )

    assert_form_invalid(response, DUPLICATE_MSG)
    assert _reload(session, first).name == "Sample_One"


def test_edit_keeping_own_name_is_allowed(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    sample.name = "Keep_My_Name"
    session.commit()

    response = post_form(
        client,
        _edit_path(sample.id),
        _payload(sample.name, C.SampleStatus.STORED.id),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/samples/{sample.id}")
    assert _reload(session, sample).status == C.SampleStatus.STORED


def test_edit_same_name_in_another_project_is_allowed(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    other_project = create_project(session, user)
    taken = create_sample(session, user, other_project)
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    taken.name = "Shared_Name"
    sample.name = "Sample_Here"
    session.commit()

    response = post_form(
        client,
        _edit_path(sample.id),
        _payload(taken.name),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/samples/{sample.id}")
    assert _reload(session, sample).name == "Shared_Name"


def test_edit_invalid_characters_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    session.commit()

    response = post_form(
        client,
        _edit_path(sample.id),
        _payload("Invalid Sample!"),
        token=user_token,
    )

    assert_form_invalid(response, "Invalid character in name")
    assert _reload(session, sample).name == sample.name


def test_edit_requires_name(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    session.commit()

    response = post_form(client, _edit_path(sample.id), {}, token=user_token)

    assert_form_invalid(response)
    assert "Sample Name is required" in response.text
    assert _reload(session, sample).name == sample.name


def test_edit_name_min_length(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    session.commit()

    response = post_form(
        client,
        _edit_path(sample.id),
        _payload("ab"),
        token=user_token,
    )

    assert_form_invalid(response)
    assert "at least 3" in response.text
    assert _reload(session, sample).name == sample.name


def test_edit_name_max_length(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    session.commit()

    response = post_form(
        client,
        _edit_path(sample.id),
        _payload("x" * (models.Sample.name.type.length + 1)),
        token=user_token,
    )

    assert_form_invalid(response)
    assert "at most 64" in response.text
    assert _reload(session, sample).name == sample.name


def test_edit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    session.commit()

    response = post_form_csrf_mismatch(
        client,
        _edit_path(sample.id),
        _payload("CSRF Sample"),
        token=user_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert _reload(session, sample).name == sample.name