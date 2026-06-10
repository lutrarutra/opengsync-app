from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from pydantic import ValidationError
from loguru import logger

from opengsync_db import exceptions as db_exc

from . import config, responses, exceptions as exc

async def default_exception_handler(request: Request, e: Exception) -> JSONResponse:
    logger.error(f"Unhandled exception {type(e)}: {e}")
    if config.settings.ENVIRONMENT != "production":
        return JSONResponse(content={"detail": str(e)}, status_code=500)
    
    return JSONResponse(
        content={"detail": "An unexpected error occurred. Please try again later."}, status_code=500,
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    error_summary = [
        {"field": ".".join(map(str, err["loc"])), "msg": err["msg"]} 
        for err in exc.errors()
    ]
    logger.error(f"Validation error for request {request.url}: {error_summary}")
    return JSONResponse(content={"detail": error_summary}, status_code=422)

async def db_model_not_found_handler(request: Request, exc: db_exc.ModelNotFoundException) -> JSONResponse:
    logger.debug(f"Database model not found: {exc.message}")
    return JSONResponse(content={"detail": exc.message}, status_code=404)

async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

async def response_validation_exception_handler(request: Request, exc: ResponseValidationError) -> JSONResponse:
    error_summary = [{"field": ".".join(map(str, err["loc"])), "msg": err["msg"]} for err in exc.errors()]
    logger.error(f"Response Validation Error: {error_summary}")
    return JSONResponse(content={"detail": "Internal Server Error."}, status_code=500)

async def pydantic_validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    error_summary = [{"field": ".".join(map(str, err["loc"])), "msg": err["msg"]} for err in exc.errors()]
    logger.error(f"Pydantic Validation Error: {error_summary}")
    return JSONResponse(content={"detail": "Internal Server Error."}, status_code=500)

async def UserNotAuthenticatedException_handler(request: Request, exc: Exception) -> Response:
    if request.headers.get("HX-Request") == "true":
        return await responses.htmx_response(redirect="login_page", status=303)
    return await responses.html_response(redirect="login_page", status=303)

async def form_validation_exception_handler(request: Request, exc: exc.FormValidationException) -> Response:
    return await exc.form.make_response()