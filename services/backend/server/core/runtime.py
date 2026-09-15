from typing import Literal

from fastapi import Request as FastApiRequest, FastAPI as FastApiApp
from starlette.datastructures import State
from redis import ConnectionPool
from typing import cast

from opengsync_db import SyncDBHandler, models

from . import mailer, audit, secrets

class AppState(State):
    db_handler: SyncDBHandler
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
    form_data: dict | None
    audit: audit.AuditLogger | None
    clear_rate_limit: bool
    rate_limit_keys: list[str]
    share_audit_key: str | None
    share_audit_ttl: int | None
    cache_key: str | None
    cache_expire: int | None
    csrf_token: str | None
    
    @classmethod
    def apply_defaults(cls, state: State):
        if not hasattr(state, "current_user"):
            state.current_user = NOT_CHECKED
        if not hasattr(state, "audit"):
            state.audit = None
        if not hasattr(state, "clear_rate_limit"):
            state.clear_rate_limit = False
        if not hasattr(state, "rate_limit_keys"):
            state.rate_limit_keys = []
        if not hasattr(state, "share_audit_key"):
            state.share_audit_key = None
        if not hasattr(state, "share_audit_ttl"):
            state.share_audit_ttl = None
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
