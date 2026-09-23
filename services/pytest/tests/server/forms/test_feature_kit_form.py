"""FeatureKitForm: create + edit, insider required, identifier validation."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q

from ...db.create_units import create_feature_kit
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

PREFIX = "/htmx/features"
CREATE_POST_PATH = f"{PREFIX}/feature-kit"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _payload(**overrides: object) -> dict[str, str]:
    data = {"name": "MyFeatureKit", "identifier": "FK-001", "feature_type_id": "1"}
    data.update({k: str(v) for k, v in overrides.items() if v is not None})
    return data


# ── Render Create ────────────────────────────────────────────────────────────


def test_create_render_requires_insider(client: TestClient, user_token: str):
    assert get(client, f"{PREFIX}/create-kit", user_token).status_code == 403


def test_create_render_allows_insider(client: TestClient, insider_token: str):
    response = get(client, f"{PREFIX}/create-kit", insider_token)
    assert response.status_code == 200
    assert 'name="name"' in response.text


# ── Create ────────────────────────────────────────────────────────────────────


def test_create_persists(client: TestClient, session: SyncSession, insider_token: str):
    response = post_form(client, CREATE_POST_PATH, _payload(identifier="FK-NEW"), token=insider_token)

    assert_htmx_redirect(response)
    assert_flash(response, "Feature kit created successfully.", "success")
    assert session.first(Q.feature_kit.select(name="MyFeatureKit")) is not None


def test_create_requires_insider(client: TestClient, session: SyncSession, user_token: str):
    response = post_form(client, CREATE_POST_PATH, _payload(identifier="FK-NO"), token=user_token)
    assert response.status_code == 403


def test_create_identifier_no_hash(client: TestClient, insider_token: str):
    response = post_form(client, CREATE_POST_PATH, _payload(identifier="#bad"), token=insider_token)
    assert_form_invalid(response)


def test_create_duplicate_identifier(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_feature_kit(session)
    session.commit()

    response = post_form(client, CREATE_POST_PATH, _payload(identifier=kit.identifier), token=insider_token)
    assert_form_invalid(response)


def test_create_duplicate_name(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_feature_kit(session)
    session.commit()

    response = post_form(client, CREATE_POST_PATH, _payload(name=kit.name, identifier="Unique"), token=insider_token)
    assert_form_invalid(response)


def test_create_csrf_mismatch(client: TestClient, session: SyncSession, insider_token: str):
    response = post_form_csrf_mismatch(client, CREATE_POST_PATH, _payload(), token=insider_token)
    assert_form_invalid(response)


# ── Render Edit ──────────────────────────────────────────────────────────────


def test_edit_render(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_feature_kit(session)
    session.commit()

    response = get(client, f"{PREFIX}/{kit.id}/edit-feature-kit", insider_token)
    assert response.status_code == 200
    assert kit.name in response.text


def test_edit_render_unknown_is_404(client: TestClient, insider_token: str):
    assert get(client, f"{PREFIX}/999999/edit-feature-kit", insider_token).status_code == 404


# ── Edit ──────────────────────────────────────────────────────────────────────


def test_edit_persists(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_feature_kit(session)
    session.commit()

    response = post_form(client, f"{PREFIX}/{kit.id}/edit-feature-kit",
                         _payload(name="UpdatedFK", identifier="FK-UPD", feature_type_id="2"), token=insider_token)

    assert_htmx_redirect(response)
    assert_flash(response, "Feature kit updated successfully.", "success")
    session.expire_all()
    updated = session.get_one(Q.feature_kit.select(id=kit.id))
    assert updated.name == "UpdatedFK"


def test_edit_unknown_is_404(client: TestClient, insider_token: str):
    response = post_form(client, f"{PREFIX}/999999/edit-feature-kit", _payload(), token=insider_token)
    assert response.status_code == 404


def test_edit_duplicate_name(client: TestClient, session: SyncSession, insider_token: str):
    kit1 = create_feature_kit(session)
    kit2 = create_feature_kit(session)
    session.commit()

    response = post_form(client, f"{PREFIX}/{kit2.id}/edit-feature-kit",
                         _payload(name=kit1.name, identifier="Unique"), token=insider_token)
    assert_form_invalid(response)


def test_edit_csrf_mismatch(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_feature_kit(session)
    session.commit()

    response = post_form_csrf_mismatch(client, f"{PREFIX}/{kit.id}/edit-feature-kit",
                                       _payload(), token=insider_token)
    assert_form_invalid(response)