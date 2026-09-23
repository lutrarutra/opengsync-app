"""ProtocolForm: create + edit, no auth gate, name uniqueness."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q

from ...db.create_units import create_protocol
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

PREFIX = "/htmx/protocols"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _payload(**overrides: object) -> dict[str, str]:
    data = {"name": "TestProtocol", "service_type": "0", "read_structure": ""}
    data.update({k: str(v) for k, v in overrides.items() if v is not None})
    return data


def test_create_render(client: TestClient, user_token: str):
    response = get(client, f"{PREFIX}/create", user_token)
    assert response.status_code == 200
    assert 'name="name"' in response.text


def test_create_persists(client: TestClient, session: SyncSession, user_token: str):
    response = post_form(client, f"{PREFIX}/create", _payload(), token=user_token)
    assert_htmx_redirect(response)
    assert_flash(response, "Protocol Created!", "success")
    assert session.first(Q.protocol.select(name="TestProtocol")) is not None


def test_create_name_too_short(client: TestClient, user_token: str):
    response = post_form(client, f"{PREFIX}/create", _payload(name="ab"), token=user_token)
    assert_form_invalid(response)


def test_create_duplicate_name(client: TestClient, session: SyncSession, user_token: str):
    p = create_protocol(session)
    session.commit()
    response = post_form(client, f"{PREFIX}/create", _payload(name=p.name), token=user_token)
    assert_form_invalid(response)
    assert "already exists" in response.text


def test_create_csrf_mismatch(client: TestClient, session: SyncSession, user_token: str):
    response = post_form_csrf_mismatch(client, f"{PREFIX}/create", _payload(), token=user_token)
    assert_form_invalid(response)


def test_edit_render(client: TestClient, session: SyncSession, user_token: str):
    p = create_protocol(session)
    session.commit()
    response = get(client, f"{PREFIX}/{p.id}/edit", user_token)
    assert response.status_code == 200
    assert p.name in response.text


def test_edit_render_unknown_is_404(client: TestClient, user_token: str):
    assert get(client, f"{PREFIX}/999999/edit", user_token).status_code == 404


def test_edit_persists(client: TestClient, session: SyncSession, user_token: str):
    p = create_protocol(session)
    session.commit()
    response = post_form(client, f"{PREFIX}/{p.id}/edit", _payload(name="Updated"), token=user_token)
    assert_htmx_redirect(response)
    assert_flash(response, "Protocol Updated!", "success")
    session.expire_all()
    assert session.get_one(Q.protocol.select(id=p.id)).name == "Updated"


def test_edit_unknown_is_404(client: TestClient, user_token: str):
    response = post_form(client, f"{PREFIX}/999999/edit", _payload(), token=user_token)
    assert response.status_code == 404


def test_edit_duplicate_name(client: TestClient, session: SyncSession, user_token: str):
    p1 = create_protocol(session)
    p2 = create_protocol(session)
    session.commit()
    response = post_form(client, f"{PREFIX}/{p2.id}/edit", _payload(name=p1.name), token=user_token)
    assert_form_invalid(response)


def test_edit_csrf_mismatch(client: TestClient, session: SyncSession, user_token: str):
    p = create_protocol(session)
    session.commit()
    response = post_form_csrf_mismatch(client, f"{PREFIX}/{p.id}/edit", _payload(), token=user_token)
    assert_form_invalid(response)