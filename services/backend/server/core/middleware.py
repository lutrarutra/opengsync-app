import time
from typing import Callable, Awaitable

from sqlalchemy import inspect
from starlette.types import ASGIApp, Receive, Scope, Send, Message
from starlette.datastructures import UploadFile
from fastapi import Response, Request
from starlette.background import BackgroundTask, BackgroundTasks
from loguru import logger

from opengsync_db import models, SyncSession

from . import runtime, secrets, config

async def state_initialization_middleware(request: runtime.Request, call_next: Callable[[runtime.Request], Awaitable[Response]]):
    runtime.RequestState.apply_defaults(request.state)
    response = await call_next(request)
    return response

def add_background_task(response: Response, task: BackgroundTask):
    if response.background is None:
        response.background = task
    elif isinstance(response.background, BackgroundTasks):
        response.background.add_task(task.func, *task.args, **task.kwargs)
    else:
        old_task = response.background
        combined_tasks = BackgroundTasks()
        combined_tasks.add_task(old_task.func, *old_task.args, **old_task.kwargs)
        combined_tasks.add_task(task.func, *task.args, **task.kwargs)
        response.background = combined_tasks

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
            scope = {**scope, "root_path": prefix}

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
    return response

def __save_audit_log(request: runtime.Request, user_id, status_code: int):
    route = request.scope.get("route")
    logger.bind(
        audit=True,
        user_id=user_id,
        method=request.method.upper(),
        route=getattr(route, "path", request.url.path),
        query_params=dict(request.query_params),
        ip=request.headers.get("x-real-ip") or (request.client.host if request.client else "1.1.1.1"),
        agent=request.headers.get("user-agent", "unknown"),
        process_time=request.headers.get("x-process-time"),
        status_code=status_code,
    ).info("request completed")

async def audit_middleware(request: runtime.Request, call_next: Callable[[runtime.Request], Awaitable[Response]]):
    response = await call_next(request)

    if response.status_code >= 400:

        user_id = None
        if (current_user := getattr(request.state, "current_user", None)) is not None:
            if isinstance(current_user, models.User):
                user_id = inspect(current_user).dict["id"]
        
        add_background_task(
            response,
            BackgroundTask(
                __save_audit_log, 
                request=request,
                user_id=user_id, 
                status_code=response.status_code
            )
        )            
    return response

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
    """Commit or roll back, then close dependency-created DB sessions."""

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

        request = Request(scope, receive=receive)
        status_code: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            session: SyncSession | None = getattr(request.state, "db_session", None,)

            if session is not None:
                try:
                    rollback = getattr(request.state, "rollback", False)

                    if not rollback and status_code is not None and 200 <= status_code < 300:
                        session.commit()
                    else:
                        session.rollback()
                finally:
                    session.close()