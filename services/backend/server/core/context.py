from contextlib import contextmanager
from typing import Any, Generator

from contextvars import ContextVar
from fastapi import Request, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from opengsync_db import SyncSession

_request_ctx_var: ContextVar[Request] = ContextVar("request")
_response_ctx_var: ContextVar[Response] = ContextVar("response")

class Context:
    @property
    def request(self) -> Request:
        return _request_ctx_var.get()
    
    @property
    def response(self) -> Response:
        return _response_ctx_var.get()
    
    @property
    def tags(self) -> list[str]:
        return self.request.scope.get("tags", [])
    
    @property
    def sid(self) -> str | None:
        return self.request.cookies.get("session_id")

    @property
    def session(self) -> SyncSession:
        request = ctx.request

        if (session := getattr(request.state, "db_session", None)) is None:
            session = request.app.state.db_handler.get_session()
            request.state.db_session = session

        return session
    
ctx = Context()

@contextmanager
def bind(request: Request, response: Response | None = None) -> Generator[Response, None, None]:
    """Temporarily bind request context for code running outside the ASGI task."""
    response = response or Response()
    request_token = _request_ctx_var.set(request)
    response_token = _response_ctx_var.set(response)
    try:
        yield response
    finally:
        _request_ctx_var.reset(request_token)
        _response_ctx_var.reset(response_token)

class ContextMiddleware:
    """Expose the current request and a temporary response through ``ctx``.

    This is deliberately a pure ASGI middleware.  ``BaseHTTPMiddleware`` runs
    the downstream application in a separate task, which makes ContextVar
    lifetime and exception handling dependent on task boundaries.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        temp_response = Response()

        request_token = _request_ctx_var.set(request)
        response_token = _response_ctx_var.set(temp_response)

        async def send_with_context(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                skip_headers = {b"content-length", b"content-type", b"connection"}

                for header, value in temp_response.raw_headers:
                    if header == b"set-cookie":
                        headers.append((header, value))
                    elif header.lower() not in skip_headers:
                        headers = [
                            (existing_header, existing_value)
                            for existing_header, existing_value in headers
                            if existing_header.lower() != header.lower()
                        ]
                        headers.append((header, value))

                message = {**message, "headers": headers}

            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        finally:
            _request_ctx_var.reset(request_token)
            _response_ctx_var.reset(response_token)


def get_request_context() -> dict[str, Any]:
    from ..core import runtime

    request = ctx.request
    
    if (current_user := getattr(request.state, "current_user", runtime.NOT_CHECKED)) == runtime.NOT_CHECKED:
        current_user = None

    context = {
        "request": request,
        "current_user": current_user
    }

    if hasattr(request.state, "db_session"):
        context["session"] = request.state.db_session

    return context