"""FlowCellDesignForm: edit-only, insider required."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q

from ...db.create_units import create_flow_cell_design
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

EDIT_PATH = "/htmx/flow_cell_design/edit-flow-cell-design"


def _url(base: str, **params: object) -> str:
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return f"{base}?{qs}" if qs else base


def _payload(**overrides: object) -> dict[str, str]:
    data = {"name": "UpdatedDesign", "flow_cell_type_id": "-1"}
    data.update({k: str(v) for k, v in overrides.items() if v is not None})
    return data


def test_render_edit_requires_insider(client: TestClient, session: SyncSession, user_token: str):
    d = create_flow_cell_design(session)
    session.commit()
    response = get(client, _url(EDIT_PATH, flow_cell_design_id=d.id), user_token)
    assert response.status_code == 403


def test_render_edit_shows_existing(client: TestClient, session: SyncSession, insider_token: str):
    d = create_flow_cell_design(session)
    session.commit()
    response = get(client, _url(EDIT_PATH, flow_cell_design_id=d.id), insider_token)
    assert response.status_code == 200
    assert d.name in response.text


def test_render_edit_unknown_is_404(client: TestClient, insider_token: str):
    response = get(client, _url(EDIT_PATH, flow_cell_design_id=999999), insider_token)
    assert response.status_code == 404


def test_edit_persists(client: TestClient, session: SyncSession, insider_token: str):
    d = create_flow_cell_design(session)
    session.commit()
    response = post_form(client, _url(EDIT_PATH, flow_cell_design_id=d.id), _payload(name="Changed"), token=insider_token)
    assert_htmx_redirect(response)
    assert_flash(response, "Changes Saved!", "success")
    session.expire_all()
    assert session.get_one(Q.flow_cell_design.select(id=d.id)).name == "Changed"


def test_edit_requires_insider(client: TestClient, session: SyncSession, user, user_token: str):
    d = create_flow_cell_design(session)
    session.commit()
    response = post_form(client, _url(EDIT_PATH, flow_cell_design_id=d.id), _payload(), token=user_token)
    assert response.status_code == 403


def test_edit_unknown_is_404(client: TestClient, insider_token: str):
    response = post_form(client, _url(EDIT_PATH, flow_cell_design_id=999999), _payload(), token=insider_token)
    assert response.status_code == 404


def test_edit_csrf_mismatch(client: TestClient, session: SyncSession, insider_token: str):
    d = create_flow_cell_design(session)
    session.commit()
    response = post_form_csrf_mismatch(client, _url(EDIT_PATH, flow_cell_design_id=d.id), _payload(), token=insider_token)
    assert_form_invalid(response)