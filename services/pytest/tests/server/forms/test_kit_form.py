"""KitForm: create + edit, insider required, identifier validation."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q

from ...db.create_units import create_kit
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

PREFIX = "/htmx/kits"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _payload(**overrides: object) -> dict[str, str]:
    data = {"name": "TestKitName", "identifier": "ID-12345"}
    data.update({k: str(v) for k, v in overrides.items() if v is not None})
    return data


# ── Render Create ────────────────────────────────────────────────────────────


def test_create_render_requires_insider(client: TestClient, user_token: str):
    assert get(client, f"{PREFIX}/create", user_token).status_code == 403


def test_create_render_allows_insider(client: TestClient, insider_token: str):
    response = get(client, f"{PREFIX}/create", insider_token)
    assert response.status_code == 200
    assert 'name="name"' in response.text
    assert 'name="identifier"' in response.text


# ── Create ────────────────────────────────────────────────────────────────────


def test_create_persists(client: TestClient, session: SyncSession, insider_token: str):
    response = post_form(client, f"{PREFIX}/create", _payload(), token=insider_token)

    assert_htmx_redirect(response)
    assert_flash(response, "Kit created successfully.", "success")
    assert session.first(Q.kit.select(name="TestKitName")) is not None


def test_create_requires_insider(client: TestClient, session: SyncSession, user_token: str):
    response = post_form(client, f"{PREFIX}/create", _payload(), token=user_token)
    assert response.status_code == 403
    assert session.first(Q.kit.select(name="TestKitName")) is None


def test_create_name_too_short(client: TestClient, session: SyncSession, insider_token: str):
    """KitForm name field has no min_length, so short names pass through."""
    response = post_form(client, f"{PREFIX}/create", _payload(name="ab"), token=insider_token)
    assert_htmx_redirect(response)
    assert session.first(Q.kit.select(name="ab")) is not None


def test_create_identifier_no_hash(client: TestClient, session: SyncSession, insider_token: str):
    response = post_form(client, f"{PREFIX}/create", _payload(identifier="#bad"), token=insider_token)
    assert_form_invalid(response)


def test_create_identifier_no_comma(client: TestClient, session: SyncSession, insider_token: str):
    response = post_form(client, f"{PREFIX}/create", _payload(identifier="a,b"), token=insider_token)
    assert_form_invalid(response)


def test_create_duplicate_identifier(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_kit(session)
    session.commit()

    response = post_form(client, f"{PREFIX}/create", _payload(identifier=kit.identifier), token=insider_token)
    assert_form_invalid(response)
    assert "identifier already exists" in response.text


def test_create_duplicate_name(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_kit(session)
    session.commit()

    response = post_form(client, f"{PREFIX}/create", _payload(name=kit.name), token=insider_token)
    assert_form_invalid(response)
    assert "name already exists" in response.text


def test_create_csrf_mismatch(client: TestClient, session: SyncSession, insider_token: str):
    response = post_form_csrf_mismatch(client, f"{PREFIX}/create", _payload(), token=insider_token)
    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, "error")


# ── Render Edit ──────────────────────────────────────────────────────────────


def test_edit_render(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_kit(session)
    session.commit()

    response = get(client, f"{PREFIX}/{kit.id}/edit-kit", insider_token)
    assert response.status_code == 200
    assert kit.name in response.text
    assert kit.identifier in response.text


def test_edit_render_unknown_is_404(client: TestClient, insider_token: str):
    assert get(client, f"{PREFIX}/999999/edit-kit", insider_token).status_code == 404


# ── Edit ──────────────────────────────────────────────────────────────────────


def test_edit_persists(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_kit(session)
    session.commit()

    response = post_form(client, f"{PREFIX}/{kit.id}/edit-kit", _payload(name="Updated", identifier="NewID"), token=insider_token)

    assert_htmx_redirect(response)
    assert_flash(response, "Kit updated successfully.", "success")
    session.expire_all()
    updated = session.get_one(Q.kit.select(id=kit.id))
    assert updated.name == "Updated"
    assert updated.identifier == "NewID"


def test_edit_unknown_is_404(client: TestClient, insider_token: str):
    response = post_form(client, f"{PREFIX}/999999/edit-kit", _payload(), token=insider_token)
    assert response.status_code == 404


def test_edit_duplicate_name(client: TestClient, session: SyncSession, insider_token: str):
    kit1 = create_kit(session)
    kit2 = create_kit(session)
    session.commit()

    response = post_form(client, f"{PREFIX}/{kit2.id}/edit-kit", _payload(name=kit1.name, identifier="Unique"), token=insider_token)
    assert_form_invalid(response)
    assert "name already exists" in response.text


def test_edit_duplicate_identifier(client: TestClient, session: SyncSession, insider_token: str):
    kit1 = create_kit(session)
    kit2 = create_kit(session)
    session.commit()

    response = post_form(client, f"{PREFIX}/{kit2.id}/edit-kit", _payload(name="Unique", identifier=kit1.identifier), token=insider_token)
    assert_form_invalid(response)
    assert "identifier already exists" in response.text


def test_edit_identifier_no_hash(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_kit(session)
    session.commit()

    response = post_form(client, f"{PREFIX}/{kit.id}/edit-kit", _payload(identifier="#bad"), token=insider_token)
    assert_form_invalid(response)


def test_edit_csrf_mismatch(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_kit(session)
    session.commit()

    response = post_form_csrf_mismatch(client, f"{PREFIX}/{kit.id}/edit-kit", _payload(), token=insider_token)
    assert_form_invalid(response)