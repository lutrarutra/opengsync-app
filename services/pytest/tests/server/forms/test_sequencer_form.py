"""SequencerForm: create + edit, insider required for create/edit, not for render edit."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_sequencer
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

PREFIX = "/htmx/sequencers"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _payload(**overrides: object) -> dict[str, str]:
    data = {"name": "MySequencer", "model": "1", "ip_address": ""}
    data.update({k: str(v) for k, v in overrides.items() if v is not None})
    return data


def test_create_render_requires_insider(client: TestClient, user_token: str):
    assert get(client, f"{PREFIX}/create", user_token).status_code == 403


def test_create_render_allows_insider(client: TestClient, insider_token: str):
    response = get(client, f"{PREFIX}/create", insider_token)
    assert response.status_code == 200
    assert 'name="name"' in response.text


def test_create_persists(client: TestClient, session: SyncSession, insider_token: str):
    response = post_form(client, f"{PREFIX}/create", _payload(), token=insider_token)
    assert_htmx_redirect(response)
    assert_flash(response, "Sequencer", "success")  # flash starts with "Sequencer"
    assert session.first(Q.sequencer.select(name="MySequencer")) is not None


def test_create_requires_insider(client: TestClient, session: SyncSession, user_token: str):
    response = post_form(client, f"{PREFIX}/create", _payload(), token=user_token)
    assert response.status_code == 403


def test_create_duplicate_name(client: TestClient, session: SyncSession, insider_token: str):
    s = create_sequencer(session)
    session.commit()
    response = post_form(client, f"{PREFIX}/create", _payload(name=s.name), token=insider_token)
    assert_form_invalid(response)


def test_create_csrf_mismatch(client: TestClient, session: SyncSession, insider_token: str):
    response = post_form_csrf_mismatch(client, f"{PREFIX}/create", _payload(), token=insider_token)
    assert_form_invalid(response)


def test_edit_render(client: TestClient, session: SyncSession, user_token: str):
    s = create_sequencer(session)
    session.commit()
    response = get(client, f"{PREFIX}/{s.id}/edit", user_token)
    assert response.status_code == 200
    assert s.name in response.text


def test_edit_render_unknown_is_404(client: TestClient, user_token: str):
    assert get(client, f"{PREFIX}/999999/edit", user_token).status_code == 404


def test_edit_persists(client: TestClient, session: SyncSession, insider_token: str):
    s = create_sequencer(session)
    session.commit()
    response = post_form(client, f"{PREFIX}/{s.id}/edit", _payload(name="Updated"), token=insider_token)
    assert_htmx_redirect(response)
    assert_flash(response, "Sequencer updated.", "success")
    session.expire_all()
    assert session.get_one(Q.sequencer.select(id=s.id)).name == "Updated"


def test_edit_requires_insider(client: TestClient, session: SyncSession, user_token: str):
    s = create_sequencer(session)
    session.commit()
    response = post_form(client, f"{PREFIX}/{s.id}/edit", _payload(), token=user_token)
    assert response.status_code == 403


def test_edit_unknown_is_404(client: TestClient, insider_token: str):
    response = post_form(client, f"{PREFIX}/999999/edit", _payload(), token=insider_token)
    assert response.status_code == 404


def test_edit_duplicate_name(client: TestClient, session: SyncSession, insider_token: str):
    s1 = create_sequencer(session)
    s2 = create_sequencer(session)
    session.commit()
    response = post_form(client, f"{PREFIX}/{s2.id}/edit", _payload(name=s1.name), token=insider_token)
    assert_form_invalid(response)


def test_edit_csrf_mismatch(client: TestClient, session: SyncSession, insider_token: str):
    s = create_sequencer(session)
    session.commit()
    response = post_form_csrf_mismatch(client, f"{PREFIX}/{s.id}/edit", _payload(), token=insider_token)
    assert_form_invalid(response)