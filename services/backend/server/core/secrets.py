from passlib.context import CryptContext
import jwt
import datetime as dt
import bcrypt
import secrets

from loguru import logger

from opengsync_db.categories import UserRole
from opengsync_db import models

from .config import settings
from . import exceptions as exc

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def hash_api_token(token: str) -> str:
    return pwd_context.hash(token)

def verify_api_token(token: str, hashed_token: str) -> bool:
    return pwd_context.verify(token, hashed_token)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def generate_api_token() -> str:
    return "cf-" + secrets.token_urlsafe(32)

def url_safe_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)

def create_password_reset_token(user_id: int, valid_minutes: int = 60 * 24) -> str:
    expire = dt.datetime.now() + dt.timedelta(minutes=valid_minutes)
    payload = {
        "user_id": user_id,
        "exp": expire,
        "action": "password_reset"
    }
    if not settings.SECRET_KEY:
        raise ValueError("SECRET_KEY is not set in settings.")
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def verify_password_reset_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("action") != "password_reset":
            return None
        return payload.get("user_id")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    
def generate_registration_token(email: str, role: UserRole, valid_minutes: int = 60 * 24) -> str:
    expire = dt.datetime.now() + dt.timedelta(minutes=valid_minutes)
    payload = {
        "email": email,
        "role": role.id,
        "exp": expire,
        "action": "registration"
    }
    if not settings.SECRET_KEY:
        raise ValueError("SECRET_KEY is not set in settings.")
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def verify_registration_token(token: str) -> tuple[str, UserRole] | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("action") != "registration":
            return None
        email = payload.get("email")
        role_id = payload.get("role")
        if email is None or role_id is None:
            return None
        role = UserRole.get(role_id)
        if role is None:
            return None
        return email, role
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    

def create_login_token(user: models.User, valid_days: int = 7) -> str:
    expire = dt.datetime.now() + dt.timedelta(days=valid_days)
    payload = {
        "id": user.id,
        "exp": expire.timestamp(),
        "username": user.email,
        "role": user.role.id
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def validate_login_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if (user_id := payload.get("id")) is None:
            logger.warning("Token missing user ID")
            raise exc.HTTPException(status_code=401, detail="Invalid token")
        if (username := payload.get("username")) is None:
            logger.warning("Token missing username")
            raise exc.HTTPException(status_code=401, detail="Invalid token")
        if (role := payload.get("role")) is None:
            logger.warning("Token missing user role")
            raise exc.HTTPException(status_code=401, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise exc.HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        logger.warning("Invalid token")
        raise exc.HTTPException(status_code=401, detail="Invalid token")
    
    return {"id": user_id, "username": username, "role": role}


class BcryptCompat:
    """Drop-in replacement for flask_bcrypt.Bcrypt, compatible with
    passwords hashed by flask_bcrypt using default settings.

    Defaults: rounds=12, prefix=b'2b', handle_long_passwords=False
    """

    def __init__(
        self,
        rounds: int = 12,
        prefix: bytes = b"2b",
        handle_long_passwords: bool = False,
    ):
        self._log_rounds = rounds
        self._prefix = prefix
        self._handle_long_passwords = handle_long_passwords

    def generate_password_hash(self, password: str, rounds: int | None = None) -> str:
        if not password:
            raise ValueError("Password must be non-empty.")

        if rounds is None:
            rounds = self._log_rounds

        password_bytes = password.encode("utf-8")

        if self._handle_long_passwords:
            import hashlib
            password_bytes = hashlib.sha256(password_bytes).hexdigest().encode("utf-8")

        salt = bcrypt.gensalt(rounds=rounds, prefix=self._prefix)
        return bcrypt.hashpw(password_bytes, salt).decode("utf-8")

    def check_password_hash(self, pw_hash: bytes | str, password: str) -> bool:
        if isinstance(pw_hash, str):
            pw_hash = pw_hash.encode("utf-8")

        password_bytes = password.encode("utf-8")

        if self._handle_long_passwords:
            import hashlib
            password_bytes = hashlib.sha256(password_bytes).hexdigest().encode("utf-8")

        return bcrypt.checkpw(password_bytes, pw_hash)