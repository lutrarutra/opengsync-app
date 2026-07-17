from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from pydantic import ValidationError
from loguru import logger

from sqlalchemy.exc import MissingGreenlet

from opengsync_db import exceptions as db_exc

from . import config, responses, exceptions as exc

def default_exception_handler(request: Request, e: Exception) -> JSONResponse:
    if config.settings.ENVIRONMENT != "production":
        return JSONResponse(content={"detail": str(e)}, status_code=500)
    return JSONResponse(content={"detail": "An unexpected error occurred. Please try again later."}, status_code=500)

def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    error_summary = [
        {"field": ".".join(map(str, err["loc"])), "msg": err["msg"]} 
        for err in exc.errors()
    ]
    logger.error(f"Validation error for request {request.url}: {error_summary}")
    return JSONResponse(content={"detail": error_summary}, status_code=422)

def db_model_not_found_handler(request: Request, exc: db_exc.ModelNotFoundException) -> JSONResponse:
    logger.debug(f"Database model not found: {exc.message}")
    return JSONResponse(content={"detail": exc.message}, status_code=404)

def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

def response_validation_exception_handler(request: Request, exc: ResponseValidationError) -> JSONResponse:
    error_summary = [{"field": ".".join(map(str, err["loc"])), "msg": err["msg"]} for err in exc.errors()]
    logger.error(f"Response Validation Error: {error_summary}")
    return JSONResponse(content={"detail": "Internal Server Error."}, status_code=500)

def pydantic_validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    error_summary = [{"field": ".".join(map(str, err["loc"])), "msg": err["msg"]} for err in exc.errors()]
    logger.error(f"Pydantic Validation Error: {error_summary}")
    return JSONResponse(content={"detail": "Internal Server Error."}, status_code=500)

def UserNotAuthenticatedException_handler(request: Request, exc: Exception) -> Response:
    if request.headers.get("HX-Request") == "true":
        return responses.htmx_response(redirect=responses.url_for("login_page"), status=303)
    return responses.html_response(redirect=responses.url_for("login_page"), status=303)

def form_validation_exception_handler(request: Request, exc: exc.FormValidationException) -> Response:
    logger.debug(f"Form validation failed: {exc.form.errors}")
    request.state.rollback = True
    return exc.form.invalid_response_handler(request, exc)

def missing_greenlet_handler(request: Request, exc: MissingGreenlet) -> Response:
    model_name, attr_name = _extract_model_and_attr(exc)
    short_tb = _format_short_traceback(exc)
    logger.error(
        f"MissingGreenlet: lazy loading '{attr_name}' on '{model_name}' is not possible "
        f"with an async session. Use selectinload() or orm.with_expression(). "
        f"URL: {request.url}\n{short_tb}"
    )

    message = (
        f"Lazy loading '{attr_name}' on '{model_name}' is not supported with async sessions. "
        "Use selectinload() or orm.with_expression() to eagerly load this attribute."
    )

    if request.headers.get("HX-Request") == "true":
        return responses.HTMLResponse(
            content=f"<div class='alert alert-danger'><pre>{message}\n\n{short_tb}</pre></div>",
            status_code=500,
        )
    return JSONResponse(content={"detail": message, "traceback": short_tb}, status_code=500)


def _extract_model_and_attr(exc: MissingGreenlet) -> tuple[str, str]:
    """Walk the traceback to find the model class and attribute that triggered lazy loading."""
    tb = exc.__traceback__
    while tb is not None:
        frame = tb.tb_frame
        locals_ = frame.f_locals
        if "instance" in locals_ and "self" in locals_:
            instance = locals_["instance"]
            descriptor = locals_["self"]
            if hasattr(descriptor, "key") and hasattr(instance, "__class__"):
                return instance.__class__.__name__, descriptor.key
        tb = tb.tb_next
    return "Unknown", "unknown"


def _format_short_traceback(exc: MissingGreenlet) -> str:
    """Format a short traceback showing the app frames around the lazy load."""
    frames = []
    tb = exc.__traceback__
    while tb is not None:
        frames.append(tb)
        tb = tb.tb_next

    if not frames:
        return ""

    # Find the first frame inside sqlalchemy/orm (the lazy-load trigger)
    lazy_idx = len(frames) - 1
    for i, f in enumerate(frames):
        if "sqlalchemy/orm/" in (f.tb_frame.f_code.co_filename or ""):
            lazy_idx = i
            break

    # Take 2 caller frames before + the lazy load frame + 1 after
    start = max(0, lazy_idx - 2)
    end = min(len(frames), lazy_idx + 2)
    selected = frames[start:end]

    lines = []
    for f in selected:
        fname = f.tb_frame.f_code.co_filename
        parts = fname.split("/")
        short_name = "/".join(parts[-3:]) if len(parts) > 3 else fname
        lineno = f.tb_lineno
        func = f.tb_frame.f_code.co_name
        lines.append(f"  {short_name}:{lineno} in {func}()")

    header = f"Traceback (most recent call last, showing {len(selected)} frames):"
    return "\n".join([header] + lines)

