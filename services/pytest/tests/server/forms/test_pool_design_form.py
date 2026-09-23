"""PoolDesignForm: create + edit, insider only, cycle counts."""

from fastapi.testclient import TestClient

import sqlalchemy as sa

from opengsync_db import SyncSession, models, queries as Q

from ...db.create_units import create_pool_design
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

CREATE_PATH = "/htmx/pool_design/create-pool-design"
EDIT_PATH = "/htmx/pool_design/edit-pool-design"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _url(base: str, **params: object) -> str:
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return f"{base}?{qs}" if qs else base


def _payload(**overrides: object) -> dict[str, str]:
    data = {
        "pool_design_name": "MyDesign",
        "r1_cycles": "101", "i1_cycles": "8",
        "i2_cycles": "8", "r2_cycles": "101",
        "num_m_requested_reads": "50", "pool_id": "",
    }
    data.update({k: str(v) for k, v in overrides.items() if v is not None})
    return data


def test_render_create_requires_insider(client: TestClient, user_token: str):
    response = get(client, CREATE_PATH, user_token)
    assert response.status_code == 403


def test_render_create_shows_form(client: TestClient, insider_token: str):
    response = get(client, CREATE_PATH, insider_token)
    assert response.status_code == 200
    assert 'name="pool_design_name"' in response.text


def test_create_persists(client: TestClient, session: SyncSession, insider_token: str):
    response = post_form(client, CREATE_PATH, _payload(), token=insider_token)
    assert_htmx_redirect(response)
    assert_flash(response, "Design Created!", "success")
    assert session.first(sa.select(models.PoolDesign).where(models.PoolDesign.name == "MyDesign")) is not None


def test_create_requires_insider(client: TestClient, session: SyncSession, user_token: str):
    response = post_form(client, CREATE_PATH, _payload(), token=user_token)
    assert response.status_code == 403


def test_create_csrf_mismatch(client: TestClient, session: SyncSession, insider_token: str):
    response = post_form_csrf_mismatch(client, CREATE_PATH, _payload(), token=insider_token)
    assert_form_invalid(response)


def test_render_edit_shows_existing(client: TestClient, session: SyncSession, insider_token: str):
    d = create_pool_design(session)
    session.commit()
    response = get(client, _url(EDIT_PATH, pool_design_id=d.id), insider_token)
    assert response.status_code == 200
    assert d.name in response.text


def test_render_edit_unknown_is_404(client: TestClient, insider_token: str):
    response = get(client, _url(EDIT_PATH, pool_design_id=999999), insider_token)
    assert response.status_code == 404


def test_edit_persists(client: TestClient, session: SyncSession, insider_token: str):
    d = create_pool_design(session)
    session.commit()
    response = post_form(client, _url(EDIT_PATH, pool_design_id=d.id), _payload(pool_design_name="Updated"), token=insider_token)
    assert_htmx_redirect(response)
    assert_flash(response, "Changes Saved!", "success")
    session.expire_all()
    assert session.get_one(Q.pool_design.select(id=d.id)).name == "Updated"


def test_edit_csrf_mismatch(client: TestClient, session: SyncSession, insider_token: str):
    d = create_pool_design(session)
    session.commit()
    response = post_form_csrf_mismatch(client, _url(EDIT_PATH, pool_design_id=d.id), _payload(), token=insider_token)
    assert_form_invalid(response)