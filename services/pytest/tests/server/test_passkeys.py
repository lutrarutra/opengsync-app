"""Passkeys (WebAuthn): registration, login, CSRF, management and password-reset cleanup."""

from typing import Any

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q, models

from ..conftest import PASSWORD
from ._http import CSRF, assert_cookie_set, assert_flash, delete, get, post_form, set_cookie_header
from ._passkey import GOOGLE_PASSWORD_MANAGER, SoftAuthenticator, b64url_decode

REGISTER_OPTIONS = "/api/passkeys/register/options"
REGISTER_VERIFY = "/api/passkeys/register/verify"
LOGIN_OPTIONS = "/api/passkeys/login/options"
LOGIN_VERIFY = "/api/passkeys/login/verify"
LIST_PATH = "/htmx/passkeys/list"
EXPIRED_MSG = "Passkey request expired, please try again."


def _post_json(
    client: TestClient,
    path: str,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    csrf: str | None = CSRF,
):
    cookies = {"csrf_token": CSRF}
    if token:
        cookies["access_token"] = token
    headers = {"X-CSRF-Token": csrf} if csrf is not None else {}
    return client.post(path, json=body or {}, headers=headers, cookies=cookies, follow_redirects=False)


def _register(client: TestClient, token: str, authenticator: SoftAuthenticator, conditional: bool = False):
    options = _post_json(client, REGISTER_OPTIONS, {"conditional": conditional}, token=token)
    assert options.status_code == 200, options.text
    return _post_json(client, REGISTER_VERIFY, authenticator.create(options.json()["options"]), token=token)


def _login_options(client: TestClient) -> dict:
    response = _post_json(client, LOGIN_OPTIONS)
    assert response.status_code == 200, response.text
    return response.json()["options"]


def _seed_passkey(session: SyncSession, user: models.User, authenticator: SoftAuthenticator) -> models.UserPasskey:
    """Store `authenticator`'s credential for `user` directly in the DB."""
    db_user = session.get_one(Q.user.select(id=user.id))
    if db_user.webauthn_user_handle is None:
        db_user.webauthn_user_handle = b"handle-" + str(user.id).encode()
    authenticator.user_handle = db_user.webauthn_user_handle
    passkey = session.save(Q.passkey.create(
        user=db_user,
        credential_id=authenticator.credential_id,
        public_key=authenticator.cose_public_key,
        sign_count=0,
        name="Passkey",
    ), flush=True)
    session.commit()
    return passkey


def _passkeys(session: SyncSession, user_id: int) -> list[models.UserPasskey]:
    session.expire_all()
    return list(session.get_all(Q.passkey.select(user_id=user_id), limit=None))


# --------------------------------------------------------------------------- registration


def test_registration_options_require_discoverable_credential(client: TestClient, user, user_token: str):
    response = _post_json(client, REGISTER_OPTIONS, token=user_token)

    assert response.status_code == 200
    data = response.json()
    options = data["options"]
    assert options["rp"]["id"] == "testserver"
    assert options["user"]["name"] == user.email
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["attestation"] == "none"
    assert options["excludeCredentials"] == []
    assert data["has_passkeys"] is False
    assert data["credential_ids"] == []
    assert b64url_decode(data["user_handle"]) == b64url_decode(options["user"]["id"])


def test_user_handle_is_stable_and_not_derived_from_user(client: TestClient, session: SyncSession, user, user_token: str):
    first = _post_json(client, REGISTER_OPTIONS, token=user_token).json()["options"]["user"]["id"]
    second = _post_json(client, REGISTER_OPTIONS, token=user_token).json()["options"]["user"]["id"]

    assert first == second
    handle = b64url_decode(first)
    assert len(handle) == 32
    assert user.email.encode() not in handle
    session.expire_all()
    assert session.get_one(Q.user.select(id=user.id)).webauthn_user_handle == handle


def test_register_passkey(client: TestClient, session: SyncSession, user, user_token: str):
    authenticator = SoftAuthenticator(aaguid=GOOGLE_PASSWORD_MANAGER)

    response = _register(client, user_token, authenticator)

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Google Password Manager"
    [passkey] = _passkeys(session, user.id)
    assert passkey.credential_id == authenticator.credential_id
    assert passkey.aaguid == GOOGLE_PASSWORD_MANAGER
    assert passkey.transport_list == ["internal", "hybrid"]
    assert passkey.last_used_utc is None


def test_registration_options_exclude_existing_passkeys(client: TestClient, user, user_token: str):
    authenticator = SoftAuthenticator()
    assert _register(client, user_token, authenticator).status_code == 200

    data = _post_json(client, REGISTER_OPTIONS, token=user_token).json()

    assert data["has_passkeys"] is True
    [excluded] = data["options"]["excludeCredentials"]
    assert b64url_decode(excluded["id"]) == authenticator.credential_id
    assert data["credential_ids"] == [excluded["id"]]


def test_register_same_credential_twice_rejected(client: TestClient, session: SyncSession, user, user_token: str):
    authenticator = SoftAuthenticator()
    assert _register(client, user_token, authenticator).status_code == 200

    response = _register(client, user_token, authenticator)

    assert response.status_code == 400
    assert response.json()["detail"] == "This passkey is already registered."
    assert len(_passkeys(session, user.id)) == 1


def test_register_requires_login(client: TestClient):
    assert _post_json(client, REGISTER_OPTIONS).status_code == 401
    assert _post_json(client, REGISTER_VERIFY, SoftAuthenticator().create({
        "challenge": "AAAA", "user": {"id": "AAAA"},
    })).status_code == 401


def test_register_without_csrf_header_rejected(client: TestClient, user_token: str):
    assert _post_json(client, REGISTER_OPTIONS, token=user_token, csrf=None).status_code == 403
    assert _post_json(client, REGISTER_OPTIONS, token=user_token, csrf="wrong").status_code == 403


def test_register_wrong_origin_rejected(client: TestClient, session: SyncSession, user, user_token: str):
    response = _register(client, user_token, SoftAuthenticator(origin="https://evil.example"))

    assert response.status_code == 400
    assert _passkeys(session, user.id) == []


def test_register_wrong_rp_id_rejected(client: TestClient, session: SyncSession, user, user_token: str):
    response = _register(client, user_token, SoftAuthenticator(rp_id="evil.example"))

    assert response.status_code == 400
    assert _passkeys(session, user.id) == []


def test_register_challenge_is_single_use(client: TestClient, session: SyncSession, user, user_token: str):
    options = _post_json(client, REGISTER_OPTIONS, token=user_token).json()["options"]
    assert _post_json(client, REGISTER_VERIFY, SoftAuthenticator().create(options), token=user_token).status_code == 200

    response = _post_json(client, REGISTER_VERIFY, SoftAuthenticator().create(options), token=user_token)

    assert response.status_code == 400
    assert response.json()["detail"] == EXPIRED_MSG
    assert len(_passkeys(session, user.id)) == 1


def test_register_challenge_of_other_user_rejected(
    client: TestClient, session: SyncSession, user, user_2, user_token: str, user_2_token: str,
):
    options = _post_json(client, REGISTER_OPTIONS, token=user_token).json()["options"]

    response = _post_json(client, REGISTER_VERIFY, SoftAuthenticator().create(options), token=user_2_token)

    assert response.status_code == 400
    assert _passkeys(session, user.id) == []
    assert _passkeys(session, user_2.id) == []


def test_conditional_registration_allows_missing_user_presence(client: TestClient, session: SyncSession, user, user_token: str):
    options = _post_json(client, REGISTER_OPTIONS, {"conditional": True}, token=user_token).json()["options"]

    response = _post_json(client, REGISTER_VERIFY, SoftAuthenticator().create(options, user_present=False), token=user_token)

    assert response.status_code == 200, response.text
    assert len(_passkeys(session, user.id)) == 1


def test_modal_registration_requires_user_presence(client: TestClient, session: SyncSession, user, user_token: str):
    options = _post_json(client, REGISTER_OPTIONS, {"conditional": False}, token=user_token).json()["options"]

    response = _post_json(client, REGISTER_VERIFY, SoftAuthenticator().create(options, user_present=False), token=user_token)

    assert response.status_code == 400
    assert _passkeys(session, user.id) == []


# --------------------------------------------------------------------------- login


def test_login_options_allow_any_discoverable_credential(client: TestClient):
    options = _login_options(client)

    assert options["rpId"] == "testserver"
    assert options.get("allowCredentials", []) == []


def test_login_with_passkey(client: TestClient, session: SyncSession, user, user_token: str):
    authenticator = SoftAuthenticator()
    assert _register(client, user_token, authenticator).status_code == 200

    response = _post_json(client, LOGIN_VERIFY, authenticator.get(_login_options(client)))

    assert response.status_code == 200, response.text
    assert response.json()["redirect"].endswith("/")
    assert_cookie_set(response, "access_token")
    assert_flash(response, "Logged In!", category="success")
    assert "passkey_upgrade" not in set_cookie_header(response)
    [passkey] = _passkeys(session, user.id)
    assert passkey.sign_count == 1
    assert passkey.last_used_utc is not None


def test_login_token_from_passkey_authenticates(client: TestClient, user, user_token: str):
    from server.core import secrets

    authenticator = SoftAuthenticator()
    assert _register(client, user_token, authenticator).status_code == 200
    response = _post_json(client, LOGIN_VERIFY, authenticator.get(_login_options(client)))

    payload = secrets.validate_login_token(response.cookies["access_token"])
    assert payload["id"] == user.id


def test_login_without_csrf_header_rejected(client: TestClient):
    assert _post_json(client, LOGIN_OPTIONS, csrf=None).status_code == 403


def test_login_assertion_replay_rejected(client: TestClient, session: SyncSession, user):
    authenticator = SoftAuthenticator()
    _seed_passkey(session, user, authenticator)
    assertion = authenticator.get(_login_options(client))
    assert _post_json(client, LOGIN_VERIFY, assertion).status_code == 200

    response = _post_json(client, LOGIN_VERIFY, assertion)

    assert response.status_code == 400
    assert response.json()["detail"] == EXPIRED_MSG
    assert "access_token" not in set_cookie_header(response)


def test_login_with_unissued_challenge_rejected(client: TestClient, session: SyncSession, user):
    authenticator = SoftAuthenticator()
    _seed_passkey(session, user, authenticator)

    response = _post_json(client, LOGIN_VERIFY, authenticator.get({"challenge": "bm90LWlzc3VlZA"}))

    assert response.status_code == 400
    assert response.json()["detail"] == EXPIRED_MSG


def test_login_unknown_passkey_tells_client_to_forget_it(client: TestClient):
    response = _post_json(client, LOGIN_VERIFY, SoftAuthenticator().get(_login_options(client), user_handle=b"x"))

    assert response.status_code == 404
    data = response.json()
    assert data["unknown_credential"] is True
    assert data["rp_id"] == "testserver"
    assert "access_token" not in set_cookie_header(response)


def test_login_bad_signature_rejected(client: TestClient, session: SyncSession, user):
    authenticator = SoftAuthenticator()
    _seed_passkey(session, user, authenticator)

    response = _post_json(client, LOGIN_VERIFY, authenticator.get(_login_options(client), tamper=True))

    assert response.status_code == 400
    assert "access_token" not in set_cookie_header(response)


def test_login_wrong_origin_rejected(client: TestClient, session: SyncSession, user):
    authenticator = SoftAuthenticator()
    _seed_passkey(session, user, authenticator)
    authenticator.origin = "https://evil.example"

    response = _post_json(client, LOGIN_VERIFY, authenticator.get(_login_options(client)))

    assert response.status_code == 400
    assert "access_token" not in set_cookie_header(response)


def test_login_user_handle_mismatch_rejected(client: TestClient, session: SyncSession, user):
    authenticator = SoftAuthenticator()
    _seed_passkey(session, user, authenticator)

    response = _post_json(client, LOGIN_VERIFY, authenticator.get(_login_options(client), user_handle=b"someone-else"))

    assert response.status_code == 400
    assert "access_token" not in set_cookie_header(response)


def test_login_deactivated_user_rejected(client: TestClient, session: SyncSession, deactivated_user):
    authenticator = SoftAuthenticator()
    _seed_passkey(session, deactivated_user, authenticator)

    response = _post_json(client, LOGIN_VERIFY, authenticator.get(_login_options(client)))

    assert response.status_code == 403
    assert response.json()["detail"] == "Account is deactivated. Please contact us to activate your account."
    assert "access_token" not in set_cookie_header(response)


def test_password_login_requests_passkey_upgrade(client: TestClient, user):
    response = post_form(client, "/htmx/auth/login", {"email": user.email, "password": PASSWORD})

    assert response.status_code == 204
    assert_cookie_set(response, "access_token")
    assert_cookie_set(response, "passkey_upgrade")


def test_login_form_offers_passkey_autofill(client: TestClient):
    response = get(client, "/htmx/auth/login")

    assert response.status_code == 200
    assert 'autocomplete="username webauthn"' in response.text
    assert "passkey-login-btn" in response.text


def test_pages_include_passkey_config(client: TestClient):
    response = get(client, "/auth/login")

    assert response.status_code == 200
    assert 'id="passkey-config"' in response.text
    assert "/api/passkeys/login/options" in response.text


# --------------------------------------------------------------------------- management


def test_owner_sees_passkey_list(client: TestClient, session: SyncSession, user, user_token: str):
    authenticator = SoftAuthenticator(aaguid=GOOGLE_PASSWORD_MANAGER)
    assert _register(client, user_token, authenticator).status_code == 200

    response = get(client, LIST_PATH, token=user_token, params={"user_id": user.id})

    assert response.status_code == 200
    assert "Google Password Manager" in response.text
    assert "passkey-register-btn" in response.text
    assert "data-signal-user-handle" in response.text


def test_other_user_cannot_see_passkeys(client: TestClient, user, user_2_token: str):
    response = get(client, LIST_PATH, token=user_2_token, params={"user_id": user.id})

    assert response.status_code == 403


def test_admin_sees_passkeys_without_register_button(client: TestClient, session: SyncSession, user, admin_token: str):
    _seed_passkey(session, user, SoftAuthenticator())

    response = get(client, LIST_PATH, token=admin_token, params={"user_id": user.id})

    assert response.status_code == 200
    assert "Passkey" in response.text
    assert "passkey-register-btn" not in response.text
    # Only the owner's browser should sync its password manager.
    assert "data-signal-user-handle" not in response.text


def test_owner_deletes_passkey(client: TestClient, session: SyncSession, user, user_token: str):
    passkey = _seed_passkey(session, user, SoftAuthenticator())

    response = delete(client, f"/htmx/passkeys/{passkey.id}", token=user_token, htmx=True)

    assert response.status_code == 200
    assert_flash(response, "Passkey removed.")
    assert "No passkeys registered." in response.text
    assert _passkeys(session, user.id) == []


def test_other_user_cannot_delete_passkey(client: TestClient, session: SyncSession, user, user_2_token: str):
    passkey = _seed_passkey(session, user, SoftAuthenticator())

    response = delete(client, f"/htmx/passkeys/{passkey.id}", token=user_2_token, htmx=True)

    assert response.status_code == 403
    assert len(_passkeys(session, user.id)) == 1


def test_deleted_passkey_cannot_log_in(client: TestClient, session: SyncSession, user, user_token: str):
    authenticator = SoftAuthenticator()
    passkey = _seed_passkey(session, user, authenticator)
    assert delete(client, f"/htmx/passkeys/{passkey.id}", token=user_token, htmx=True).status_code == 200

    response = _post_json(client, LOGIN_VERIFY, authenticator.get(_login_options(client)))

    assert response.status_code == 404
    assert response.json()["unknown_credential"] is True


# --------------------------------------------------------------------------- password reset


def test_password_reset_deletes_passkeys(client: TestClient, session: SyncSession, user, user_2):
    from server.core import secrets

    authenticator = SoftAuthenticator()
    _seed_passkey(session, user, authenticator)
    _seed_passkey(session, user_2, SoftAuthenticator())
    token = secrets.create_password_reset_token(user_id=user.id)

    response = post_form(
        client, f"/htmx/auth/reset-password/{token}",
        {"email": user.email, "password": "new-password1", "confirm": "new-password1"},
    )

    assert response.status_code == 204
    assert _passkeys(session, user.id) == []
    assert len(_passkeys(session, user_2.id)) == 1
    # The handle survives so the password manager can be told which passkeys are gone.
    assert session.get_one(Q.user.select(id=user.id)).webauthn_user_handle is not None
    login = _post_json(client, LOGIN_VERIFY, authenticator.get(_login_options(client)))
    assert login.status_code == 404


def test_password_change_keeps_passkeys(client: TestClient, session: SyncSession, user, user_token: str):
    _seed_passkey(session, user, SoftAuthenticator())

    response = post_form(
        client, "/htmx/auth/change-password",
        {"current_password": PASSWORD, "new_password": "new-password1", "confirm_new_password": "new-password1"},
        token=user_token, params={"user_id": user.id},
    )

    assert response.status_code == 204, response.text
    assert len(_passkeys(session, user.id)) == 1


def test_deleting_user_deletes_passkeys(session: SyncSession, user):
    _seed_passkey(session, user, SoftAuthenticator())
    session.delete(session.get_one(Q.user.select(id=user.id)), flush=True)
    session.commit()

    assert _passkeys(session, user.id) == []
