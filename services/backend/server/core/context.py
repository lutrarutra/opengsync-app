from typing import Any

from contextvars import ContextVar
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..core import runtime

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
    
ctx = Context()

class ContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        temp_response = Response() 
        
        request_token = _request_ctx_var.set(request)
        response_token = _response_ctx_var.set(temp_response)
        
        try:
            actual_response = await call_next(request)
            
            skip_headers = {'content-length', 'content-type', 'connection'}

            for header, value in temp_response.headers.items():
                if header.lower() not in skip_headers:
                    actual_response.headers[header] = value
            
            for header, value in temp_response.raw_headers:
                if header == b"set-cookie":
                    actual_response.raw_headers.append((header, value))
                    
            return actual_response
        finally:
            _request_ctx_var.reset(request_token)
            _response_ctx_var.reset(response_token)


def get_request_context() -> dict[str, Any]:
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