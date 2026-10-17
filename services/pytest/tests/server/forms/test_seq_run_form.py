"""SeqRunForm: create + edit, insider required."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_seq_run
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

PREFIX = "/htmx/seq-runs"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _payload(**overrides: object) -> dict[str, str]:
    data = {
        "experiment_name": "TestExp", "status": "1", "instrument_name": "Inst1",
        "run_folder": "/run", "flowcell_id": "FC1", "read_type": "1",
    }
    data.update({k: str(v) for k, v in overrides.items() if v is not None})
    return data


def test_render_create_requires_insider(client: TestClient, user_token: str):
    assert get(client, f"{PREFIX}/create", user_token).status_code == 403


def test_render_create_allows_insider(client: TestClient, insider_token: str):
    response = get(client, f"{PREFIX}/create", insider_token)
    assert response.status_code == 200
    assert 'name="experiment_name"' in response.text


def test_create_requires_insider(client: TestClient, session: SyncSession, user_token: str):
    response = post_form(client, f"{PREFIX}/create", _payload(), token=user_token)
    assert response.status_code == 403


def test_create_csrf_mismatch(client: TestClient, session: SyncSession, insider_token: str):
    response = post_form_csrf_mismatch(client, f"{PREFIX}/create", _payload(), token=insider_token)
    assert_form_invalid(response)


def test_edit_render_shows_existing(client: TestClient, session: SyncSession, user_token: str):
    sr = create_seq_run(session)
    session.commit()
    response = get(client, f"{PREFIX}/{sr.id}/edit", user_token)
    assert response.status_code == 200
    assert sr.experiment_name in response.text


def test_edit_render_unknown_is_404(client: TestClient, user_token: str):
    assert get(client, f"{PREFIX}/999999/edit", user_token).status_code == 404


def test_edit_requires_insider(client: TestClient, session: SyncSession, user_token: str):
    sr = create_seq_run(session)
    session.commit()
    response = post_form(client, f"{PREFIX}/{sr.id}/edit", _payload(), token=user_token)
    assert response.status_code == 403


def test_edit_unknown_is_404(client: TestClient, insider_token: str):
    response = post_form(client, f"{PREFIX}/999999/edit", _payload(), token=insider_token)
    assert response.status_code == 404


def test_edit_csrf_mismatch(client: TestClient, session: SyncSession, insider_token: str):
    sr = create_seq_run(session)
    session.commit()
    response = post_form_csrf_mismatch(client, f"{PREFIX}/{sr.id}/edit", _payload(), token=insider_token)
    assert_form_invalid(response)