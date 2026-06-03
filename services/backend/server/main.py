from fastapi import FastAPI, APIRouter, HTTPException, Query, Depends
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, ValidationError
from loguru import logger

from opengsync_db import exceptions as db_exc

from .core import lifespan, config, middleware, handlers, dependencies, exceptions as exc
from . import routes


app = FastAPI(lifespan=lifespan.lifespan)

app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.state_initialization_middleware)  # type: ignore
app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.audit_middleware)  # type: ignore

app.exception_handler(Exception)(handlers.default_exception_handler)
app.exception_handler(ResponseValidationError)(handlers.response_validation_exception_handler)
app.exception_handler(ValidationError)(handlers.pydantic_validation_exception_handler)
app.exception_handler(HTTPException)(handlers.http_exception_handler)
app.exception_handler(RequestValidationError)(handlers.validation_exception_handler)
app.exception_handler(exc.UserNotAuthenticatedException)(handlers.UserNotAuthenticatedException_handler)
app.exception_handler(db_exc.ElementDoesNotExist)(handlers.db_model_not_found_handler)

class ErrorResponse(BaseModel):
    detail: str

page_router = APIRouter(responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
htmx_router = APIRouter(prefix="/htmx", responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
api_router = APIRouter(prefix="/api", responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})

if config.settings.ENVIRONMENT != "production":
    @api_router.get("/invalidate-cache")
    def invalidate_cache(
        cache_invalidate: list[str] = Depends(dependencies.invalidate_cache),
        key: str | None = Query(None, description="Optional query string to further specify the cache entry to invalidate")
    ):
        if key is None:
            logger.debug("Invalidating all cache")
            cache_invalidate.append("*")
        else:
            logger.debug(f"Invalidating cache with key: {key}")
            cache_invalidate.append(key)

        return {"message": "ok"}

api_router.get("/health")(lambda: {"status": "ok"})

page_router.include_router(routes.pages.router)

app.include_router(api_router)
app.include_router(page_router)
app.include_router(htmx_router)

from opengsync_db import models

@app.get("/")
def dashboard(
    current_user: models.User | None = Depends(dependencies.get_user)
):
    if not current_user:
        raise exc.UserNotAuthenticatedException()
    
    return {"message": f"Welcome to your dashboard, {current_user.name}!"}
