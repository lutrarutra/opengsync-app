"""A software WebAuthn authenticator producing real (fmt "none") create()/get() responses."""

import base64
import hashlib
import json
import os

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

# TestClient's default base URL.
RP_ID = "testserver"
ORIGIN = "http://testserver"

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_AT = 0x40

GOOGLE_PASSWORD_MANAGER = "ea9b8d66-4d01-1d21-3ce4-b6b48cb575d4"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class SoftAuthenticator:
    def __init__(self, rp_id: str = RP_ID, origin: str = ORIGIN, aaguid: str | None = None):
        self.rp_id = rp_id
        self.origin = origin
        self.aaguid = bytes.fromhex(aaguid.replace("-", "")) if aaguid else bytes(16)
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.sign_count = 0
        self.user_handle: bytes | None = None

    @property
    def cose_public_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps({
            1: 2,    # kty: EC2
            3: -7,   # alg: ES256
            -1: 1,   # crv: P-256
            -2: numbers.x.to_bytes(32, "big"),
            -3: numbers.y.to_bytes(32, "big"),
        })

    def _client_data(self, type_: str, challenge: str) -> bytes:
        return json.dumps({
            "type": type_, "challenge": challenge, "origin": self.origin, "crossOrigin": False,
        }).encode()

    def _auth_data(self, flags: int, attested: bytes = b"") -> bytes:
        return (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([flags])
            + self.sign_count.to_bytes(4, "big")
            + attested
        )

    def create(self, options: dict, *, user_present: bool = True) -> dict:
        """Answer PublicKeyCredentialCreationOptionsJSON like navigator.credentials.create()."""
        self.user_handle = b64url_decode(options["user"]["id"])
        client_data = self._client_data("webauthn.create", options["challenge"])
        flags = FLAG_AT | FLAG_UV | (FLAG_UP if user_present else 0)
        attested = (
            self.aaguid
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + self.cose_public_key
        )
        attestation_object = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": self._auth_data(flags, attested)})
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "attestationObject": b64url(attestation_object),
                "transports": ["internal", "hybrid"],
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }

    def get(self, options: dict, *, user_handle: bytes | None = None, tamper: bool = False) -> dict:
        """Answer PublicKeyCredentialRequestOptionsJSON like navigator.credentials.get()."""
        self.sign_count += 1
        client_data = self._client_data("webauthn.get", options["challenge"])
        auth_data = self._auth_data(FLAG_UP | FLAG_UV)
        signature = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        if tamper:
            auth_data = auth_data[:-1] + bytes([auth_data[-1] ^ 0x01])
        handle = user_handle if user_handle is not None else self.user_handle
        response = {
            "clientDataJSON": b64url(client_data),
            "authenticatorData": b64url(auth_data),
            "signature": b64url(signature),
        }
        if handle is not None:
            response["userHandle"] = b64url(handle)
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": response,
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }
