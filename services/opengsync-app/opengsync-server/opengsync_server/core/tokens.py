from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from opengsync_db import models, categories as cats

def generate_file_share_token(path: str, serializer: URLSafeTimedSerializer) -> str:
    return str(serializer.dumps({"path": path}))


def verify_file_share_token(token: str, max_age_hours: int, serializer: URLSafeTimedSerializer) -> str | None:
    data = serializer.loads(token, max_age=max_age_hours * 60 * 60)
    return data.get("path")


def generate_reset_token(user: models.User, serializer: URLSafeTimedSerializer) -> str:
    return str(serializer.dumps({"id": user.id, "email": user.email, "hash": user.password}))


def generate_registration_token(email: str, serializer: URLSafeTimedSerializer, role: cats.UserRoleEnum = cats.UserRole.CLIENT) -> str:
    return str(serializer.dumps({"email": email, "role": role.id}))


def verify_registration_token(token: str, serializer: URLSafeTimedSerializer) -> tuple[str, cats.UserRoleEnum] | None:
    try:
        data = serializer.loads(token, max_age=3600)
        email = data["email"]
        role = cats.UserRole.get(data.get("role", cats.UserRole.CLIENT.id))
    except SignatureExpired:
        return None
    except BadSignature:
        return None
    return email, role


def verify_reset_token(token: str, serializer: URLSafeTimedSerializer) -> tuple[int, str, str] | None:
    try:
        data = serializer.loads(token, max_age=3600)
        id = data["id"]
        email = data["email"]
        hash = data["hash"]
    except SignatureExpired:
        return None
    except BadSignature:
        return None
    return id, email, hash