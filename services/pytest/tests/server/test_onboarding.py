"""Onboarding tour progress (server/routes/api/onboarding.py, server/core/onboarding.py): the state API,
the auto-start flag set on registration and first activation, and the tour's inclusion in pages."""
import datetime as dt
import json

from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, categories as C

from ..db import create_units
from ._http import CSRF, OpenGSyncTestClient, auth, get, post_form
from ._profile import new_profile_payload
from ..conftest import PASSWORD

URL = "/api/onboarding"


def _redis(client: OpenGSyncTestClient) -> Redis:
    return Redis(connection_pool=client.app.state.redis_pool)


def _stored(client: OpenGSyncTestClient, user_id: int) -> dict | None:
    data = _redis(client).get(f"onboarding:{user_id}")
    return None if data is None else json.loads(data)  # type: ignore[arg-type]


def _store(client: OpenGSyncTestClient, user_id: int, **state) -> None:
    _redis(client).set(f"onboarding:{user_id}", json.dumps(state))


def _post(client: TestClient, token: str, body: dict, csrf: bool = True):
    headers = auth(token) if csrf else {"Cookie": f"access_token={token}; csrf_token={CSRF}"}
    return client.post(URL, json=body, headers=headers)


def test_state_is_empty_by_default(client: TestClient, user_token: str):
    response = get(client, URL, user_token)
    assert response.status_code == 200
    assert response.json() == {"status": None}


def test_save_and_read_back(client: OpenGSyncTestClient, user, user_token: str):
    response = _post(client, user_token, {"status": "PAUSED", "step": "dash.projects"})
    assert response.status_code == 200

    state = get(client, URL, user_token).json()
    assert (state["status"], state["step"], state["seq_request_id"]) == ("PAUSED", "dash.projects", None)
    assert state["updated"] is not None

    # Stored without a TTL, so volatile-lru never evicts it
    assert _redis(client).ttl(f"onboarding:{user.id}") == -1


def test_save_rejects_invalid_state(client: TestClient, user_token: str):
    assert _post(client, user_token, {"status": "DONE"}).status_code == 422
    assert _post(client, user_token, {"status": "PAUSED", "step": "<script>"}).status_code == 422
    assert _post(client, user_token, {"step": "dash.projects"}).status_code == 422


def test_save_requires_csrf_header(client: OpenGSyncTestClient, user, user_token: str):
    response = _post(client, user_token, {"status": "PAUSED"}, csrf=False)
    assert response.status_code == 403
    assert _stored(client, user.id) is None


def test_requires_login(client: TestClient):
    assert client.get(URL, headers={"Accept": "application/json"}).status_code in (401, 303)


def test_insiders_get_no_tour(client: TestClient, insider_token: str):
    assert get(client, URL, insider_token).status_code == 403
    assert _post(client, insider_token, {"status": "PAUSED"}).status_code == 403


def test_save_own_request(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request = create_units.create_seq_request(session, user)
    session.commit()

    response = _post(client, user_token, {"status": "IN_PROGRESS", "step": "request.status", "seq_request_id": seq_request.id})
    assert response.status_code == 200
    assert get(client, URL, user_token).json()["seq_request_id"] == seq_request.id


def test_save_rejects_unreadable_request(client: OpenGSyncTestClient, session: SyncSession, user, user_2, user_token: str):
    other = create_units.create_seq_request(session, user_2)
    session.commit()

    for seq_request_id in (other.id, 999_999):
        response = _post(client, user_token, {"status": "PAUSED", "step": "request.status", "seq_request_id": seq_request_id})
        assert response.status_code == 400
    assert _stored(client, user.id) is None


def test_read_drops_request_no_longer_readable(client: OpenGSyncTestClient, session: SyncSession, user, user_2, user_token: str):
    other = create_units.create_seq_request(session, user_2)
    session.commit()

    for seq_request_id in (other.id, 999_999):
        _store(client, user.id, status="PAUSED", step="request.auth_form", seq_request_id=seq_request_id)
        state = get(client, URL, user_token).json()
        # Resumes at the dashboard's create step instead
        assert (state["status"], state["step"], state["seq_request_id"]) == ("PAUSED", "dash.create", None)
        assert _stored(client, user.id)["seq_request_id"] is None  # type: ignore[index]


def test_invalid_stored_state_is_ignored(client: OpenGSyncTestClient, user, user_token: str):
    _redis(client).set(f"onboarding:{user.id}", "not json")
    assert get(client, URL, user_token).json() == {"status": None}


# ---- auto-start --------------------------------------------------------------------------------------------

def _register(client: TestClient, email: str, role: C.UserRole):
    from server.core import secrets
    token = secrets.generate_registration_token(email=email, role=role, valid_minutes=60)
    return post_form(client, f"/htmx/auth/complete-registration/{token}", {
        "email": email, "first_name": "Ada", "last_name": "Lovelace",
        "password": PASSWORD, "confirm": PASSWORD, **new_profile_payload(),
    })


def test_registration_marks_customer_new(client: OpenGSyncTestClient, session: SyncSession):
    from opengsync_db import queries as Q

    assert _register(client, "new-customer@example.com", C.UserRole.CLIENT).status_code == 204
    created = session.get_one(Q.user.select(email="new-customer@example.com"))
    assert _stored(client, created.id)["status"] == "NEW"  # type: ignore[index]


def test_registration_of_insider_is_not_marked(client: OpenGSyncTestClient, session: SyncSession):
    from opengsync_db import queries as Q

    assert _register(client, "new-insider@example.com", C.UserRole.TECHNICIAN).status_code == 204
    created = session.get_one(Q.user.select(email="new-insider@example.com"))
    assert _stored(client, created.id) is None


def _activate(client: TestClient, user):
    from server.core import secrets
    token = secrets.create_activation_token(user_id=user.id, valid_minutes=60)
    return post_form(client, f"/htmx/auth/activate/{token}", {
        "email": user.email, "password": "new-password1", "confirm": "new-password1", **new_profile_payload(),
    })


def test_first_activation_marks_new(client: OpenGSyncTestClient, user):
    # Placeholder accounts created for a request never had a password set
    assert user.pw_set_datetime is None
    assert _activate(client, user).status_code == 204
    assert _stored(client, user.id)["status"] == "NEW"  # type: ignore[index]


def test_reactivation_is_not_marked(client: OpenGSyncTestClient, session: SyncSession, user):
    user.pw_set_datetime = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=400)
    session.commit()

    assert _activate(client, user).status_code == 204
    assert _stored(client, user.id) is None


def test_login_does_not_mark(client: OpenGSyncTestClient, user):
    response = post_form(client, "/htmx/auth/login", {"email": user.email, "password": PASSWORD})
    assert response.status_code == 204
    assert _stored(client, user.id) is None


# ---- pages ---------------------------------------------------------------------------------------------------

def test_customer_dashboard_includes_tour(client: TestClient, user_token: str):
    html = get(client, "/", user_token).text
    assert 'id="onboarding-config"' in html
    assert 'id="onboarding-fab"' in html
    for anchor in ("nav-requests", "nav-projects", "dash-seq-requests", "dash-projects", "create-seq-request"):
        assert f'data-tour="{anchor}"' in html


def test_insider_dashboard_has_no_tour(client: TestClient, insider_token: str):
    html = get(client, "/", insider_token).text
    assert "onboarding-config" not in html
    assert "onboarding-fab" not in html
