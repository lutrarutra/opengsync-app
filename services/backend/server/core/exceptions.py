from typing import TYPE_CHECKING, Literal

from fastapi import HTTPException, status, Request, Response, exceptions as fastapi_exc
from loguru import logger

from . import context, responses

if TYPE_CHECKING:
    from ..forms import HTMXForm

def error_response(
    request: Request,
    status_code: int,
    message: str,
    category: Literal["info", "success", "warning", "error"] = "error",
    redirect_endpoint: str | None = None,
) -> Response:
    """Build a request-safe HTML or HTMX error response."""
    flash = responses.flash(message=message, category=category)

    with context.bind(request):
        if redirect_endpoint is not None:
            redirect = responses.url_for(redirect_endpoint)
            if request.headers.get("HX-Request") == "true":
                return responses.htmx_response(redirect=redirect, flash=flash)
            return responses.html_response(redirect=redirect, flash=flash)

        if request.headers.get("HX-Request") == "true":
            return responses.htmx_response(status=status_code, flash=flash)

        return responses.html_response(
            template="errors/page.html",
            active_page="",
            msg=message,
            code=status_code,
            status=status_code,
            flash=flash,
        )



class OpeNGSyncServerException(Exception):
    def __init__(self, message: str = "An unexpected error occurred. Please try again later."):
        super().__init__(message)
        self.message = message

    @staticmethod
    def Handler(request: Request, e: Exception) -> Response:
        logger.opt(exception=e).error(f"{request.method.upper()} {request.url.path}: {e}")
        if isinstance(e, OpeNGSyncServerException):
            message = e.message
        elif isinstance(e, HTTPException):
            message = e.detail
        else:
            message = "An unexpected error occurred. Please try again later."
        return error_response(request, status.HTTP_500_INTERNAL_SERVER_ERROR, message)
    

class FormValidationException(HTTPException):
    def __init__(
        self,
        form: "HTMXForm",
        status_code: int = status.HTTP_202_ACCEPTED,
        flash_message: str | None = None,
    ):
        super().__init__(status_code=status_code)
        self.form = form
        self.flash_message = flash_message

    @staticmethod
    def Handler(request: Request, exc: "FormValidationException") -> Response:
        logger.debug(f"Form validation failed: {exc.form.errors}")
        request.state.rollback = True
        # Exception handlers can run outside the middleware task that owns
        # the request ContextVar.  Bind the explicit request while rendering
        # the form response so templates and form helpers remain safe.
        with context.bind(request) as temp_response:
            response = exc.form.invalid_response_handler(request, exc)

        for header, value in temp_response.raw_headers:
            if header == b"set-cookie":
                response.raw_headers.append((header, value))
        return response

class NotFoundException(HTTPException):
    def __init__(self, message: str = "Not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=message)

    @staticmethod
    def Handler(request: Request, e: "NotFoundException") -> Response:
        detail = getattr(e, "detail", str(e))
        return error_response(request, status.HTTP_404_NOT_FOUND, detail, category="warning")

class UserNotAuthenticatedException(HTTPException):
    def __init__(self, message: str = "User not authenticated"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)

    @staticmethod
    def Handler(request: Request, e: "UserNotAuthenticatedException") -> Response:
        response = error_response(
            request, status.HTTP_401_UNAUTHORIZED, e.detail,
            category="warning", redirect_endpoint="login_page",
        )
        response.delete_cookie(key="access_token", path="/", samesite="lax")
        response.delete_cookie(key="csrf_token", path="/", samesite="lax")
        return response

class UserAccountSuspendedException(HTTPException):
    def __init__(self, message: str = "Your account is suspended, please contact us."):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)

    @staticmethod
    def Handler(request: Request, e: "UserAccountSuspendedException") -> Response:
        response = error_response(
            request, status.HTTP_401_UNAUTHORIZED, e.detail,
            category="warning", redirect_endpoint="login_page",
        )
        response.delete_cookie(key="access_token", path="/", samesite="lax")
        response.delete_cookie(key="csrf_token", path="/", samesite="lax")
        return response

class NoPermissionsException(HTTPException):
    def __init__(self, detail: str = "Permission denied"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    @staticmethod
    def Handler(request: Request, e: "NoPermissionsException") -> Response:
        return error_response(request, status.HTTP_403_FORBIDDEN, e.detail)

class BadRequestException(HTTPException):
    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    @staticmethod
    def Handler(request: Request, e: "BadRequestException") -> Response:
        return error_response(request, status.HTTP_400_BAD_REQUEST, e.detail)

class MethodNotAllowedException(HTTPException):
    def __init__(self, detail: str = "Method not allowed"):
        super().__init__(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail=detail)

    @staticmethod
    def Handler(request: Request, e: "MethodNotAllowedException") -> Response:
        return error_response(request, status.HTTP_405_METHOD_NOT_ALLOWED, e.detail)


def request_validation_exception_handler(
    request: Request,
    exc: fastapi_exc.RequestValidationError,
) -> Response:
    logger.debug(f"Request validation failed: {exc.errors()}")
    message = "Invalid request."
    return error_response(request, status.HTTP_422_UNPROCESSABLE_ENTITY, message)