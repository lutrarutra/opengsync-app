from typing import Literal

from fastapi import Request as FastApiRequest, FastAPI as FastApiApp
from starlette.datastructures import URL, State
from redis.asyncio import ConnectionPool
from typing import cast

from opengsync_db import AsyncDBHandler, models

from . import mailer, audit, secrets, config

class AppState(State):
    db_handler: AsyncDBHandler
    mailer: mailer.Mailer
    redis_pool: ConnectionPool
    bcrypt: secrets.BcryptCompat

class CodeFlowerServer(FastApiApp):
    @property
    def state(self) -> AppState:  # type: ignore[override]
        return cast(AppState, super().state)

NotCheckedType = Literal["NOT_CHECKED"]
NOT_CHECKED: NotCheckedType = "NOT_CHECKED"

class RequestState(State):
    current_user: models.User | None | NotCheckedType
    audit: audit.AuditLogger | None
    cache_key: str | None
    cache_expire: int | None
    
    @classmethod
    def apply_defaults(cls, state: State):
        if not hasattr(state, "current_user"):
            state.current_user = NOT_CHECKED
        if not hasattr(state, "audit"):
            state.audit = None
        if not hasattr(state, "cache_key"):
            state.cache_key = None
        if not hasattr(state, "cache_expire"):
            state.cache_expire = None

class Request(FastApiRequest):
    @property
    def app(self) -> CodeFlowerServer:
        return cast(CodeFlowerServer, super().app)
        
    @property
    def state(self) -> RequestState:
        return cast(RequestState, super().state)