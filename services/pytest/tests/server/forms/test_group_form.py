"""GroupForm: create + edit, name uniqueness, group_permissions for edit."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_group
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

PREFIX = "/htmx/groups"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _payload(**overrides: object) -> dict[str, str]:
    data = {"name": "TestGroupName", "group_type": "1"}
    data.update({k: str(v) for k, v in overrides.items() if v is not None})
    return data


def _make_owner(session: SyncSession, group: models.Group, user: models.User) -> None:
    group.user_links.append(Q.affiliation.create(user=user, group=group, type=C.AffiliationType.OWNER))
    session.save(group, flush=True)
    session.commit()


def test_create_render(client: TestClient, user_token: str):
    response = get(client, f"{PREFIX}/create", user_token)
    assert response.status_code == 200
    assert 'name="name"' in response.text


def test_create_persists(client: TestClient, session: SyncSession, user_token: str):
    response = post_form(client, f"{PREFIX}/create", _payload(), token=user_token)
    assert_htmx_redirect(response)
    assert_flash(response, "Group Created!", "success")
    assert session.first(Q.group.select(name="TestGroupName")) is not None


def test_create_name_too_short(client: TestClient, user_token: str):
    response = post_form(client, f"{PREFIX}/create", _payload(name="ab"), token=user_token)
    assert_form_invalid(response)


def test_create_duplicate_name(client: TestClient, session: SyncSession, user_token: str):
    g = create_group(session)
    session.commit()
    response = post_form(client, f"{PREFIX}/create", _payload(name=g.name), token=user_token)
    assert_form_invalid(response)


def test_create_csrf_mismatch(client: TestClient, session: SyncSession, user_token: str):
    response = post_form_csrf_mismatch(client, f"{PREFIX}/create", _payload(), token=user_token)
    assert_form_invalid(response)


def test_edit_render(client: TestClient, session: SyncSession, user_token: str):
    g = create_group(session)
    session.commit()
    response = get(client, f"{PREFIX}/{g.id}/edit", user_token)
    assert response.status_code == 200
    assert g.name in response.text


def test_edit_render_unknown_is_404(client: TestClient, user_token: str):
    assert get(client, f"{PREFIX}/999999/edit", user_token).status_code == 404


def test_edit_persists(client: TestClient, session: SyncSession, user, user_token: str):
    g = create_group(session)
    _make_owner(session, g, user)
    response = post_form(client, f"{PREFIX}/{g.id}/edit", _payload(name="UpdatedGroup"), token=user_token)
    assert_htmx_redirect(response)
    assert_flash(response, "Group Updated!", "success")
    session.expire_all()
    assert session.get_one(Q.group.select(id=g.id)).name == "UpdatedGroup"


def test_edit_unknown_is_404(client: TestClient, user_token: str):
    response = post_form(client, f"{PREFIX}/999999/edit", _payload(), token=user_token)
    assert response.status_code == 404


def test_edit_duplicate_name(client: TestClient, session: SyncSession, user, user_token: str):
    g1 = create_group(session)
    g2 = create_group(session)
    _make_owner(session, g2, user)
    response = post_form(client, f"{PREFIX}/{g2.id}/edit", _payload(name=g1.name), token=user_token)
    assert_form_invalid(response)


def test_edit_csrf_mismatch(client: TestClient, session: SyncSession, user, user_token: str):
    g = create_group(session)
    _make_owner(session, g, user)
    response = post_form_csrf_mismatch(client, f"{PREFIX}/{g.id}/edit", _payload(), token=user_token)
    assert_form_invalid(response)