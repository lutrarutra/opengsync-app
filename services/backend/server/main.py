import json

from fastapi import FastAPI, APIRouter, HTTPException, Query, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, ValidationError
from loguru import logger

from opengsync_db import exceptions as db_exc, models

from sqlalchemy.exc import MissingGreenlet

from .core import lifespan, config, middleware, handlers, dependencies, exceptions as exc, context, responses
from . import routes


app = FastAPI(lifespan=lifespan.lifespan)

app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.db_session_cleanup_middleware)  # type: ignore
app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.state_initialization_middleware)  # type: ignore
app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.audit_middleware)  # type: ignore
app.add_middleware(context.ContextMiddleware)

app.exception_handler(Exception)(handlers.default_exception_handler)
app.exception_handler(ResponseValidationError)(handlers.response_validation_exception_handler)
app.exception_handler(ValidationError)(handlers.pydantic_validation_exception_handler)
app.exception_handler(HTTPException)(handlers.http_exception_handler)
app.exception_handler(RequestValidationError)(handlers.validation_exception_handler)
app.exception_handler(exc.UserNotAuthenticatedException)(handlers.UserNotAuthenticatedException_handler)
app.exception_handler(exc.FormValidationException)(handlers.form_validation_exception_handler)
app.exception_handler(db_exc.ElementDoesNotExist)(handlers.db_model_not_found_handler)
app.exception_handler(MissingGreenlet)(handlers.missing_greenlet_handler)


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
app.include_router(routes.pages.router)
app.include_router(routes.htmx.router)

@app.get("/")
async def dashboard(
    current_user: models.User = Depends(dependencies.require_user)
):
    if current_user.is_insider():
        return await responses.html_response(template="dashboard-insider.html")
    return await responses.html_response(template="dashboard-user.html")
    

@app.get("/help")
async def help():
    return await responses.html_response(template="help.html")

@app.get("/retrieve_flash_messages")
async def retrieve_flash_messages():
    return {}, 204

@app.get("/share-status")
async def share_status_check():
    if not config.settings.app_config.canary_files:
        return json.dumps({"status": "unknown", "details": "No canary files configured"}), 200
    
    import subprocess
    def check_canary_file(filepath: str):
        try:
            result = subprocess.run(
                ['cat', filepath], 
                capture_output=True, 
                text=True, 
                timeout=2 
            )
            
            if result.returncode == 0 and result.stdout.strip() == "ok":
                return True, "online"
                
            elif result.returncode == 0:
                return False, f"File found, but contained: '{result.stdout.strip()}'"
                
            else:
                return False, "File not found or endpoint disconnected"
                
        except subprocess.TimeoutExpired:
            return False, "Timeout: Cluster is offline or hanging"
        except Exception as e:
            return False, f"Error: {str(e)}"
        
    status_report = {}
    good_count = 0
    total_count = len(config.settings.app_config.canary_files)

    for name, filepath in config.settings.app_config.canary_files.items():
        is_ok, msg = check_canary_file(filepath)
        status_report[name] = msg
        if is_ok:
            good_count += 1

    if good_count == total_count:
        return json.dumps({"status": "online", "details": status_report}), 200

    elif good_count == 0:
        return json.dumps({"status": "offline", "details": status_report}), 503

    return json.dumps({"status": "degraded", "details": status_report}), 503

@app.get("/storage-availability")
async def storage_availability_check():
    import shutil
    usage = shutil.disk_usage(config.settings.app_config.media_folder)

    # if (usage.free / usage.total) < 0.1:
    #     flash("Less than 10% of storage space is available.", "warning")

    return {
        "used": f"{usage.used / (1024**3):.1f} GB",
        "free": f"{usage.free / (1024**3):.1f} GB",
        "total": f"{usage.total / (1024**3):.1f} GB",
        "percent_used": f"{(usage.used / usage.total) * 100:.1f}%"
    }


app.mount("/static", StaticFiles(directory="/static"), name="static")