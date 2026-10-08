import time
from collections.abc import Callable, Awaitable

from sqlalchemy import inspect
from starlette.types import ASGIApp, Receive, Scope, Send, Message
from starlette.datastructures import UploadFile
from fastapi import Response
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool
from loguru import logger

from opengsync_db import models, SyncSession

from . import runtime, secrets, config, audit, redis as rds
from ..utils import share_fs_cache

async def state_initialization_middleware(request: runtime.Request, call_next: Callable[[runtime.Request], Awaitable[Response]]):
    runtime.RequestState.apply_defaults(request.state)
    response = await call_next(request)
    return response

class XForwardedPrefixMiddleware:
    """Apply a reverse proxy's URL prefix to the ASGI request scope.

    Nginx removes the public prefix when proxying to the application. Setting
    ``root_path`` restores it for FastAPI and Starlette URL generation.
    Only accept this header from a trusted reverse proxy that overwrites it.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        prefix = self._get_prefix(scope)
        if prefix is not None:
            # Mutate in place so outer layers (ServerErrorMiddleware, which
            # renders 500 pages) see the prefix too.
            scope["root_path"] = prefix

        await self.app(scope, receive, send)

    @staticmethod
    def _get_prefix(scope: Scope) -> str | None:
        raw_prefix = next(
            (
                value
                for name, value in scope.get("headers", [])
                if name.lower() == b"x-forwarded-prefix"
            ),
            None,
        )
        if raw_prefix is None:
            return None

        prefix = raw_prefix.decode("latin-1").strip()
        if not prefix or prefix == "/":
            return ""
        if (
            not prefix.startswith("/")
            or "?" in prefix
            or "#" in prefix
            or "\\" in prefix
            or "," in prefix
            or any(ord(character) < 0x20 for character in prefix)
        ):
            return None

        return prefix.rstrip("/")


async def timing_middleware(request: runtime.Request, call_next: Callable[[runtime.Request], Awaitable[Response]]):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    request.state.process_time = str(process_time)
    return response

def _write_audit_log(request: runtime.Request, status_code: int, changes: list[dict]) -> None:
    """Write one audit line for committed DB changes, explicitly audited routes and error responses."""
    if not changes and getattr(request.state, "audit", None) is None and status_code < 400:
        return

    share_key = getattr(request.state, "share_audit_key", None)
    if share_key and status_code < 400 and not changes:
        ttl = getattr(request.state, "share_audit_ttl", None) or 3600
        try:
            with rds.RedisClient(pool=request.app.state.redis_pool) as redis:
                if not share_fs_cache.claim_share_audit(redis, share_key, ttl):
                    return
        except Exception:
            logger.exception("Failed to debounce share audit for {}", share_key)

    # set by get_user_id (cookie or API token), also on routes that never load the user
    user_id = getattr(request.state, "user_id", None)
    if isinstance(current_user := getattr(request.state, "current_user", None), models.User):
        user_id = inspect(current_user).dict.get("id", user_id)

    route = request.scope.get("route")
    audit_state = getattr(request.state, "audit", None)
    logger.bind(
        audit=True,
        user_id=user_id,
        method=request.method.upper(),
        path=request.url.path,
        route=getattr(audit_state, "route", None) or getattr(route, "path", request.url.path),
        resource_id=getattr(audit_state, "resource_id", None),
        metadata=getattr(audit_state, "metadata", None) or {},
        changes=changes,
        query_params=dict(request.query_params),
        ip=request.headers.get("x-real-ip") or (request.client.host if request.client else "1.1.1.1"),
        agent=request.headers.get("user-agent", "unknown"),
        process_time=getattr(request.state, "process_time", None),
        status_code=status_code,
    ).info("audit logged")


async def parse_form_data(request: runtime.Request, call_next: Callable[[runtime.Request], Awaitable[Response]]):
    if request.method in ("POST", "PUT", "PATCH"):
        form = await request.form()
        raw = {}
        for key, value in form.items():
            if isinstance(value, UploadFile):
                raw[key] = {
                    "filename": value.filename,
                    "content": await value.read(),
                    "content_type": value.content_type,
                    "size": value.size,
                }
            else:
                raw[key] = value
        request.state.form_data = raw
    else:
        request.state.form_data = None
    return await call_next(request)


async def csrf_middleware(request: runtime.Request, call_next: Callable[[runtime.Request], Awaitable[Response]]):
    """Ensure a per-session CSRF token cookie exists for double-submit validation.
    
    Generates a token once per session (when the cookie is missing) and stashes
    it on request.state so forms can read it during the same request (the cookie
    won't be visible to request.cookies until the next request).
    """
    token = request.cookies.get("csrf_token")
    if not token:
        token = secrets.url_safe_token(32)
        request.state.new_csrf_token = token

    request.state.csrf_token = token
    
    response = await call_next(request)
    
    if getattr(request.state, "new_csrf_token", None):
        response.set_cookie(
            key="csrf_token",
            value=request.state.new_csrf_token,
            max_age=config.settings.SESSION_EXPIRE_SECONDS,
            httponly=False,
            secure=config.settings.ENVIRONMENT != "dev",
            samesite="lax",
        )
    return response


class DBSessionCleanupMiddleware:
    """Commit or roll back dependency-created DB sessions, write the audit log, then close them.

    The transaction is finished before the response start is forwarded, so a
    failed commit becomes a 500 instead of a success response for a write
    that was rolled back. It is finished once more when the request ends, to
    cover writes made while streaming the body or in background tasks.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = runtime.Request(scope, receive=receive)
        status_code: int | None = None
        commit_failed = False
        changes: list[dict] = []

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, commit_failed

            if commit_failed:
                return  # the original response was replaced by a 500

            if message["type"] == "http.response.start":
                status_code = message["status"]
                try:
                    changes.extend(await run_in_threadpool(_finish_transaction, request, status_code))
                except Exception:
                    logger.exception("Commit failed, responding with 500")
                    commit_failed = True
                    status_code = 500
                    await PlainTextResponse("Internal Server Error", status_code=500)(scope, receive, send)
                    return

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            try:
                changes.extend(await run_in_threadpool(_finish_transaction, request, status_code, True))
            finally:
                try:
                    # no status means the app raised before responding
                    await run_in_threadpool(_write_audit_log, request, status_code or 500, changes)
                except Exception:
                    logger.exception("Failed to write audit log")


def _finish_transaction(request: runtime.Request, status_code: int | None, close: bool = False) -> list[dict]:
    """Commit on 2xx (unless a rollback was requested), otherwise roll back; returns the committed changes."""
    session: SyncSession | None = getattr(request.state, "db_session", None)
    if session is None:
        return []
    try:
        if not getattr(request.state, "rollback", False) and status_code is not None and 200 <= status_code < 300:
            session.commit()
            return audit.pop_changes(session)
        session.rollback()
        return []
    finally:
        if close:
            session.close()
