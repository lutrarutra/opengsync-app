"""CommentForm: create context-aware comments on seq requests."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q

from ...db.create_units import create_seq_request
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

FORM_PATH = "/htmx/comments/comment"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _url(base: str, **params: object) -> str:
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return f"{base}?{qs}" if qs else base


def _payload(**overrides: object) -> dict[str, str]:
    data = {"comment": "Test comment text"}
    data.update({k: str(v) for k, v in overrides.items() if v is not None})
    return data


def test_render_for_own_seq_request(client: TestClient, session: SyncSession, user, user_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = get(client, _url(FORM_PATH, seq_request_id=sr.id), user_token)
    assert response.status_code == 200
    assert 'name="comment"' in response.text


def test_render_for_stranger_seq_request_denied(client: TestClient, session: SyncSession, user, user_2_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = get(client, _url(FORM_PATH, seq_request_id=sr.id), user_2_token)
    assert response.status_code == 403


def test_render_without_context_returns_400(client: TestClient, user_token: str):
    response = get(client, FORM_PATH, user_token)
    assert response.status_code == 400


def test_submit_on_own_seq_request(client: TestClient, session: SyncSession, user, user_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = post_form(client, _url(FORM_PATH, seq_request_id=sr.id), _payload(), token=user_token)
    assert_htmx_redirect(response)
    assert_flash(response, "Comment Added!", "success")
    assert session.first(Q.comment.select(author_id=user.id)) is not None


def test_submit_without_context_returns_400(client: TestClient, user_token: str):
    response = post_form(client, FORM_PATH, _payload(), token=user_token)
    assert response.status_code == 400


def test_submit_empty_comment_fails(client: TestClient, session: SyncSession, user, user_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = post_form(client, _url(FORM_PATH, seq_request_id=sr.id), _payload(comment=""), token=user_token)
    assert_form_invalid(response)


def test_submit_csrf_mismatch(client: TestClient, session: SyncSession, user, user_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = post_form_csrf_mismatch(client, _url(FORM_PATH, seq_request_id=sr.id), _payload(), token=user_token)
    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, "error")