"""MediaFileForm: upload form, WRITE on seq_request or insider required."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession

from ...db.create_units import create_seq_request
from .._http import assert_flash, assert_form_invalid, get, post_form, post_form_csrf_mismatch

UPLOAD_PATH = "/htmx/files/upload"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _url(base: str, **params: object) -> str:
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return f"{base}?{qs}" if qs else base


def _payload(**overrides: object) -> dict[str, str]:
    data = {"file_type": "1", "comment": "Test upload"}
    data.update({k: str(v) for k, v in overrides.items() if v is not None})
    return data


def test_render_for_own_seq_request(client: TestClient, session: SyncSession, user, user_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = get(client, _url(UPLOAD_PATH, seq_request_id=sr.id), user_token)
    assert response.status_code == 200
    assert 'name="file_type"' in response.text


def test_render_for_stranger_seq_request_denied(client: TestClient, session: SyncSession, user, user_2_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = get(client, _url(UPLOAD_PATH, seq_request_id=sr.id), user_2_token)
    assert response.status_code == 403


def test_render_without_context_returns_400(client: TestClient, user_token: str):
    response = get(client, UPLOAD_PATH, user_token)
    assert response.status_code == 400


def test_post_without_context_returns_400(client: TestClient, user_token: str):
    response = post_form(client, UPLOAD_PATH, _payload(), token=user_token)
    assert response.status_code == 400


def test_post_empty_file_type_fails(client: TestClient, session: SyncSession, user, user_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = post_form(client, _url(UPLOAD_PATH, seq_request_id=sr.id), _payload(file_type=""), token=user_token)
    assert_form_invalid(response)


def test_post_csrf_mismatch(client: TestClient, session: SyncSession, user, user_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = post_form_csrf_mismatch(client, _url(UPLOAD_PATH, seq_request_id=sr.id), _payload(), token=user_token)
    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, "error")