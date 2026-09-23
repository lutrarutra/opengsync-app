"""TODOCommentForm: insider-only create/edit for TODO comments on designs."""

import sqlalchemy as sa

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_pool_design, create_todo_comment
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

FORM_PATH = "/htmx/comments/form"
EDIT_PATH = "/htmx/comments/edit-form"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _url(base: str, **params: object) -> str:
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return f"{base}?{qs}" if qs else base


def _payload(**overrides: object) -> dict[str, str]:
    data = {"text": "TODO note", "status_id": str(C.TaskStatus.IN_PROGRESS.id)}
    data.update({k: str(v) for k, v in overrides.items() if v is not None})
    return data


def test_render_create_requires_insider(client: TestClient, session: SyncSession, user_token: str):
    pd = create_pool_design(session)
    session.commit()
    response = get(client, _url(FORM_PATH, pool_design_id=pd.id), user_token)
    assert response.status_code == 403


def test_render_create_shows_form(client: TestClient, session: SyncSession, insider_token: str):
    pd = create_pool_design(session)
    session.commit()
    response = get(client, _url(FORM_PATH, pool_design_id=pd.id), insider_token)
    assert response.status_code == 200
    assert 'name="text"' in response.text


def test_create_persists(client: TestClient, session: SyncSession, user, insider_token: str):
    pd = create_pool_design(session)
    session.commit()
    response = post_form(client, _url(FORM_PATH, pool_design_id=pd.id), _payload(), token=insider_token)
    assert_htmx_redirect(response)
    assert_flash(response, "Comment added!", "success")
    assert session.first(sa.select(models.TODOComment).where(models.TODOComment.text == "TODO note")) is not None


def test_create_requires_insider(client: TestClient, session: SyncSession, user_token: str):
    pd = create_pool_design(session)
    session.commit()
    response = post_form(client, _url(FORM_PATH, pool_design_id=pd.id), _payload(), token=user_token)
    assert response.status_code == 403


def test_create_csrf_mismatch(client: TestClient, session: SyncSession, insider_token: str):
    pd = create_pool_design(session)
    session.commit()
    response = post_form_csrf_mismatch(client, _url(FORM_PATH, pool_design_id=pd.id), _payload(), token=insider_token)
    assert_form_invalid(response)


def test_render_edit_shows_existing(client: TestClient, session: SyncSession, user, insider_token: str):
    pd = create_pool_design(session)
    tc = create_todo_comment(session, user, pool_design_id=pd.id)
    session.commit()
    # RenderEdit is at FORM_PATH (GET /form) with todo_comment_id, not EDIT_PATH
    response = get(client, _url(FORM_PATH, todo_comment_id=tc.id), insider_token)
    assert response.status_code == 200
    assert tc.text in response.text


def test_render_edit_unknown_is_404(client: TestClient, insider_token: str):
    response = get(client, _url(FORM_PATH, todo_comment_id=999999), insider_token)
    assert response.status_code == 404


def test_edit_persists(client: TestClient, session: SyncSession, user, insider_token: str):
    pd = create_pool_design(session)
    tc = create_todo_comment(session, user, pool_design_id=pd.id)
    session.commit()
    response = post_form(client, _url(EDIT_PATH, todo_comment_id=tc.id), _payload(text="Updated"), token=insider_token)
    assert_htmx_redirect(response)
    assert_flash(response, "Comment updated!", "success")
    session.expire_all()
    assert session.get_one(Q.todo_comment.select(id=tc.id)).text == "Updated"


def test_edit_csrf_mismatch(client: TestClient, session: SyncSession, user, insider_token: str):
    pd = create_pool_design(session)
    tc = create_todo_comment(session, user, pool_design_id=pd.id)
    session.commit()
    response = post_form_csrf_mismatch(client, _url(EDIT_PATH, todo_comment_id=tc.id), _payload(), token=insider_token)
    assert_form_invalid(response)