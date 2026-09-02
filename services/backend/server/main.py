from fastapi import FastAPI, APIRouter, HTTPException, Query, Depends, exceptions as fastapi_exc
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from loguru import logger

from opengsync_db import exceptions as db_exc, models

from .core import lifespan, config, middleware, dependencies, exceptions as exc, context, responses
from . import routes


app = FastAPI(lifespan=lifespan.lifespan)  # type: ignore
app.exception_handler(Exception)(exc.OpeNGSyncServerException.Handler)
app.exception_handler(fastapi_exc.RequestValidationError)(exc.request_validation_exception_handler)
app.exception_handler(HTTPException)(exc.OpeNGSyncServerException.Handler)

app.exception_handler(exc.UserNotAuthenticatedException)(exc.UserNotAuthenticatedException.Handler)
app.exception_handler(exc.FormValidationException)(exc.FormValidationException.Handler)
app.exception_handler(exc.UserAccountSuspendedException)(exc.UserAccountSuspendedException.Handler)
app.exception_handler(exc.NoPermissionsException)(exc.NoPermissionsException.Handler)
app.exception_handler(db_exc.NotFoundException)(exc.NotFoundException.Handler)
app.exception_handler(exc.NotFoundException)(exc.NotFoundException.Handler)

app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.timing_middleware)  # type: ignore
app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.csrf_middleware)  # type: ignore
app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.parse_form_data)  # type: ignore
app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.state_initialization_middleware)  # type: ignore
app.add_middleware(middleware.DBSessionCleanupMiddleware)
app.add_middleware(context.ContextMiddleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.audit_middleware)  # type: ignore
app.add_middleware(middleware.XForwardedPrefixMiddleware)

class ErrorResponse(BaseModel):
    detail: str

router = APIRouter(responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})

if config.settings.ENVIRONMENT != "production":
    @routes.api.router.get("/invalidate-cache")
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

routes.api.router.get("/health")(lambda: {"status": "ok"})

app.include_router(routes.api.router)
app.include_router(routes.api.tokens.router)
app.include_router(routes.pages.router)
app.include_router(routes.htmx.router)

@app.get("/")
def dashboard(
    current_user: models.User = Depends(dependencies.require_user)
):
    if current_user.is_insider:
        return responses.html_response(template="dashboard-insider.html")
    return responses.html_response(template="dashboard-user.html")
    

@app.get("/help")
def help():
    return responses.html_response(template="help.html")

@app.get("/status")
def status():
    return PlainTextResponse("OK")

if config.settings.ENVIRONMENT != "production":
    @app.get("/test")
    def test_route():
        return {"message": "This is a test route."}



if config.settings.ENVIRONMENT in ("dev", "test"):
    app.mount("/static", StaticFiles(directory="/static"), name="static")