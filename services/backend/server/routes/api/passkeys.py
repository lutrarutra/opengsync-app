"""WebAuthn (passkey) ceremonies, called with fetch() from static/js/passkey.js."""
import datetime as dt
import json
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from loguru import logger

from webauthn import verify_authentication_response, verify_registration_response
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException

from opengsync_db import models, queries as Q, SyncSession

from ...core import auth, dependencies, passkeys, responses, exceptions as exc, redis as rds

router = APIRouter(
    prefix="/passkeys", tags=["passkeys"],
    dependencies=[Depends(dependencies.verify_csrf_header), Depends(dependencies.audit_log)],
)
login_rate_limit = [Depends(dependencies.rate_limit("20/minute"))]

EXPIRED_MSG = "Passkey request expired, please try again."


class RegistrationOptionsRequest(BaseModel):
    # True for the automatic, prompt-less "save a passkey" offer after a password login.
    conditional: bool = False


@router.post("/register/options", name="passkey_register_options")
def register_options(
    request: Request,
    body: RegistrationOptionsRequest = RegistrationOptionsRequest(),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
    r: rds.RedisClient = Depends(dependencies.redis),
):
    user = session.get_one(Q.user.select(id=current_user.id))
    existing = list(session.get_all(Q.passkey.select(user_id=user.id), limit=None))
    options = passkeys.registration_options(request, r, user, existing, conditional=body.conditional)
    return {
        "options": options,
        "has_passkeys": len(existing) > 0,
        # For PublicKeyCredential.signalAllAcceptedCredentials()
        "rp_id": passkeys.rp_id(request),
        "user_handle": bytes_to_base64url(passkeys.ensure_user_handle(user)),
        "credential_ids": [bytes_to_base64url(p.credential_id) for p in existing],
    }


@router.post("/register/verify", name="passkey_register_verify")
def register_verify(
    request: Request,
    credential: dict[str, Any] = Body(...),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
    r: rds.RedisClient = Depends(dependencies.redis),
):
    try:
        parsed, challenge = passkeys.parse_registration(credential)
    except passkeys.PasskeyError as e:
        raise exc.BadRequestException(e.message)

    state = passkeys.pop_challenge(r, "reg", challenge)
    if state is None or state.get("user_id") != current_user.id:
        raise exc.BadRequestException(EXPIRED_MSG)

    try:
        verified = verify_registration_response(
            credential=parsed,
            expected_challenge=challenge,
            expected_rp_id=passkeys.rp_id(request),
            expected_origin=passkeys.expected_origins(request),
            # Conditional create (automatic upgrade) happens without a user gesture.
            require_user_presence=not state.get("conditional", False),
        )
    except WebAuthnException as e:
        logger.warning(f"Passkey registration failed for user {current_user.id}: {e}")
        raise exc.BadRequestException("Passkey could not be verified.")

    if session.exists(Q.passkey.select(credential_id=verified.credential_id)):
        raise exc.BadRequestException("This passkey is already registered.")

    user = session.get_one(Q.user.select(id=current_user.id))
    passkey = session.save(Q.passkey.create(
        user=user,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        name=passkeys.provider_name(verified.aaguid),
        transports=[t.value for t in parsed.response.transports or []],
        aaguid=verified.aaguid,
        backed_up=verified.credential_backed_up,
    ), flush=True)

    return {"id": passkey.id, "name": passkey.name}


@router.post("/login/options", name="passkey_login_options", dependencies=login_rate_limit)
def login_options(
    request: Request,
    r: rds.RedisClient = Depends(dependencies.redis),
):
    return {"options": passkeys.authentication_options(request, r)}


@router.post("/login/verify", name="passkey_login_verify", dependencies=login_rate_limit)
def login_verify(
    request: Request,
    credential: dict[str, Any] = Body(...),
    session: SyncSession = Depends(dependencies.db_session),
    r: rds.RedisClient = Depends(dependencies.redis),
):
    try:
        parsed, challenge = passkeys.parse_authentication(credential)
    except passkeys.PasskeyError as e:
        raise exc.BadRequestException(e.message)

    if passkeys.pop_challenge(r, "auth", challenge) is None:
        raise exc.BadRequestException(EXPIRED_MSG)

    if (passkey := session.first(Q.passkey.select(credential_id=parsed.raw_id))) is None:
        # e.g. deleted here or by a password reset; the client tells the password manager to forget it.
        return JSONResponse(status_code=404, content={
            "detail": "This passkey is no longer registered. Please sign in with your password.",
            "unknown_credential": True,
            "rp_id": passkeys.rp_id(request),
        })

    user = passkey.user
    user_handle = parsed.response.user_handle
    if user_handle is not None and user_handle != user.webauthn_user_handle:
        raise exc.BadRequestException("Passkey could not be verified.")

    try:
        verified = verify_authentication_response(
            credential=parsed,
            expected_challenge=challenge,
            expected_rp_id=passkeys.rp_id(request),
            expected_origin=passkeys.expected_origins(request),
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
        )
    except WebAuthnException as e:
        logger.warning(f"Passkey login failed for user {user.id}: {e}")
        raise exc.BadRequestException("Passkey could not be verified.")

    if (rejection := auth.login_rejection(user)) is not None:
        raise exc.NoPermissionsException(rejection)

    passkey.sign_count = verified.new_sign_count
    passkey.backed_up = verified.credential_backed_up
    passkey.last_used_utc = dt.datetime.now(dt.timezone.utc)

    resp = JSONResponse({"redirect": str(responses.url_for("dashboard"))})
    auth.set_login_cookie(resp, user)
    resp.set_cookie(
        key="flash_message",
        value=quote(json.dumps(responses.flash(message="Logged In!", category="success").model_dump())),
        max_age=60,
        httponly=False,
        samesite="lax",
        path="/",
    )
    return resp
