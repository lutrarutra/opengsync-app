"""WebAuthn (passkey) helpers: relying-party settings, challenge storage and option generation.

Challenges are stored in Redis keyed by the challenge itself, so several tabs can run
ceremonies at once and no extra cookie is needed. Each challenge is single-use (GETDEL).
"""
import json
import os
from typing import Any, Literal

from fastapi import Request, Response
from redis.exceptions import RedisError
from loguru import logger

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
)
from webauthn.helpers import (
    bytes_to_base64url,
    parse_authentication_credential_json,
    parse_client_data_json,
    parse_registration_credential_json,
)
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticationCredential,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from webauthn.helpers.exceptions import WebAuthnException

from opengsync_db import models

from .config import settings
from . import redis as rds

CHALLENGE_TTL_SECONDS = 10 * 60
# Set after a password login; passkey.js then offers to save a passkey to the password manager.
UPGRADE_COOKIE = "passkey_upgrade"

ChallengeKind = Literal["reg", "auth"]

# Display names for common passkey providers, keyed by AAGUID
# (see https://github.com/passkeydeveloper/passkey-authenticator-aaguids).
PROVIDER_NAMES = {
    "ea9b8d66-4d01-1d21-3ce4-b6b48cb575d4": "Google Password Manager",
    "adce0002-35bc-c60a-648b-0b25f1f05503": "Chrome on Mac",
    "fbfc3007-154e-4ecc-8c0b-6e020557d7bd": "iCloud Keychain",
    "08987058-cadc-4b81-b6e1-30de50dcbe96": "Windows Hello",
    "bada5566-a7aa-401f-bd96-45619a55120d": "1Password",
    "d548826e-79b4-db40-a3d8-11116f7e8349": "Bitwarden",
    "531126d6-e717-415c-9320-3d9aa6981239": "Dashlane",
    "fdb141b2-5d84-443e-8a35-4698c205a502": "KeePassXC",
}


class PasskeyError(Exception):
    """A ceremony could not be completed; `message` is safe to show to the user."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def rp_id(request: Request) -> str:
    return settings.WEBAUTHN_RP_ID or (request.url.hostname or "localhost")


def expected_origins(request: Request) -> list[str]:
    if settings.WEBAUTHN_ORIGINS:
        return [o.strip().rstrip("/") for o in settings.WEBAUTHN_ORIGINS.split(",") if o.strip()]
    return [f"{request.url.scheme}://{request.url.netloc}"]


def provider_name(aaguid: str | None) -> str:
    return PROVIDER_NAMES.get(aaguid or "", "Passkey")


def set_upgrade_cookie(response: Response) -> None:
    response.set_cookie(
        key=UPGRADE_COOKIE, value="1", max_age=5 * 60,
        httponly=False, secure=settings.ENVIRONMENT != "dev", samesite="lax", path="/",
    )


def _challenge_key(kind: ChallengeKind, challenge: bytes) -> str:
    return f"passkey:{kind}:{bytes_to_base64url(challenge)}"


def store_challenge(r: rds.RedisClient, kind: ChallengeKind, challenge: bytes, data: dict[str, Any]) -> None:
    r.set(_challenge_key(kind, challenge), json.dumps(data), ex=CHALLENGE_TTL_SECONDS)


def pop_challenge(r: rds.RedisClient, kind: ChallengeKind, challenge: bytes) -> dict[str, Any] | None:
    try:
        raw = r.getdel(_challenge_key(kind, challenge))
    except RedisError:
        logger.exception("Failed to read passkey challenge")
        return None
    if raw is None:
        return None
    return json.loads(raw)  # type: ignore[arg-type]


def ensure_user_handle(user: models.User) -> bytes:
    if user.webauthn_user_handle is None:
        user.webauthn_user_handle = os.urandom(32)
    return user.webauthn_user_handle


def registration_options(
    request: Request,
    r: rds.RedisClient,
    user: models.User,
    existing: list[models.UserPasskey],
    conditional: bool,
) -> dict[str, Any]:
    options = generate_registration_options(
        rp_id=rp_id(request),
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=ensure_user_handle(user),
        user_name=user.email,
        user_display_name=user.name,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            # Discoverable credential: stored in the password manager, usable without typing an email.
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        # Lets the password manager skip creating a duplicate passkey it already holds.
        exclude_credentials=[
            PublicKeyCredentialDescriptor(
                id=p.credential_id,
                transports=[AuthenticatorTransport(t) for t in p.transport_list if t in AuthenticatorTransport._value2member_map_],
            )
            for p in existing
        ],
    )
    store_challenge(r, "reg", options.challenge, {"user_id": user.id, "conditional": conditional})
    return json.loads(options_to_json(options))


def authentication_options(request: Request, r: rds.RedisClient) -> dict[str, Any]:
    # No allowCredentials: the password manager offers whichever passkey it holds for this RP.
    options = generate_authentication_options(
        rp_id=rp_id(request),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    store_challenge(r, "auth", options.challenge, {})
    return json.loads(options_to_json(options))


def parse_registration(credential: dict[str, Any]) -> tuple[RegistrationCredential, bytes]:
    """Parse a create() response and return it with the challenge it claims to answer."""
    try:
        parsed = parse_registration_credential_json(credential)
        challenge = parse_client_data_json(parsed.response.client_data_json).challenge
    except (WebAuthnException, ValueError, KeyError, TypeError):
        raise PasskeyError("Invalid passkey response.")
    return parsed, challenge


def parse_authentication(credential: dict[str, Any]) -> tuple[AuthenticationCredential, bytes]:
    """Parse a get() response and return it with the challenge it claims to answer."""
    try:
        parsed = parse_authentication_credential_json(credential)
        challenge = parse_client_data_json(parsed.response.client_data_json).challenge
    except (WebAuthnException, ValueError, KeyError, TypeError):
        raise PasskeyError("Invalid passkey response.")
    return parsed, challenge
