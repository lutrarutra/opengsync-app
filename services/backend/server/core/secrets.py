from uuid import UUID
from passlib.context import CryptContext
import jwt
import datetime as dt
import secrets

from loguru import logger

from opengsync_db.categories import UserRole

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
    

def create_login_token(user_id: UUID, username: str, user_type: UserRole, valid_days: int = 7) -> str:
    expire = dt.datetime.now() + dt.timedelta(days=valid_days)
    payload = {
        "id": str(user_id),
        "exp": expire.timestamp(),
        "username": username,
        "type": user_type
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
        if (type_ := payload.get("type")) is None:
            logger.warning("Token missing user type")
            raise exc.HTTPException(status_code=401, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise exc.HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        logger.warning("Invalid token")
        raise exc.HTTPException(status_code=401, detail="Invalid token")
    
    return {"id": user_id, "username": username, "type": type_}