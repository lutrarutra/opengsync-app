from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer
from opengsync_db import categories as cats


class AuthResponse(BaseModel):
    id: int
    username: str
    role: cats.UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)