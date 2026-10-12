import datetime as dt

from fastapi import Response
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer
from opengsync_db import categories as C, models

from . import secrets


class AuthResponse(BaseModel):
    id: int
    username: str
    role: C.UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

ACCOUNT_DEACTIVATED_MSG = "Account is deactivated. Please contact us to activate your account."


def login_rejection(user: models.User) -> str | None:
    """Return why `user` may not log in, or None if they may.

    Shared by password and passkey login. A temporary (admin-started) account is
    deactivated on its first own login attempt.
    """
    if user.role == C.UserRole.DEACTIVATED:
        return ACCOUNT_DEACTIVATED_MSG

    if user.role == C.UserRole.TEMPORARY:
        user.role = C.UserRole.DEACTIVATED
        return ACCOUNT_DEACTIVATED_MSG

    return None


def record_login(user: models.User) -> None:
    """Stamp a successful login; the worker deactivates users who stop logging in."""
    user.last_login = dt.datetime.now(dt.timezone.utc)


def set_role(user: models.User, role: C.UserRole) -> None:
    """Change `user`'s role. Reactivating restarts the inactivity window, otherwise the nightly
    job would deactivate the user again before they get a chance to log in.
    """
    if user.role == C.UserRole.DEACTIVATED and role != C.UserRole.DEACTIVATED:
        record_login(user)
    user.role = role


def set_login_cookie(response: Response, user: models.User) -> None:
    response.set_cookie(
        key="access_token",
        value=secrets.create_login_token(user),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,  # 7 days
    )
