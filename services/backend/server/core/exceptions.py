from typing import TYPE_CHECKING

from fastapi import HTTPException, status, Request, Response, exceptions as fastapi_exc
from loguru import logger

from . import responses

if TYPE_CHECKING:
    from ..forms import HTMXForm



class OpeNGSyncServerException(Exception):
    @staticmethod
    def Handler(request: Request, _: Exception) -> Response:
        flash = responses.flash(message="An unexpected error occurred. Please try again later.", category="error")
        logger.debug("An unexpected error occurred.")
        if request.headers.get("HX-Request") == "true":
            response = responses.htmx_response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, flash=flash)
        else:
            response = responses.html_response(
                template="errors/page.html",
                active_page="", msg="An unexpected error occurred. Please try again later.",
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                status=status.HTTP_500_INTERNAL_SERVER_ERROR, flash=flash
            )
        return response
    

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
        logger = request.app.state.logger
        logger.debug(f"Form validation failed: {exc.form.errors}")
        request.state.rollback = True
        return exc.form.invalid_response_handler(request, exc)

class NotFoundException(HTTPException):
    def __init__(self, message: str = "Not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=message)

    @staticmethod
    def Handler(request: Request, _: Exception) -> Response:
        flash = responses.flash(message="Not found", category="warning")
        if request.headers.get("HX-Request") == "true":
            response = responses.htmx_response(status=status.HTTP_404_NOT_FOUND, flash=flash)
        else:
            response = responses.html_response(template="errors/page.html", active_page="", msg="Not found", code=status.HTTP_404_NOT_FOUND, status=status.HTTP_404_NOT_FOUND, flash=flash)
        return response

class UserNotAuthenticatedException(HTTPException):
    def __init__(self, message: str = "User not authenticated"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)

    @staticmethod
    def Handler(request: Request, _: Exception) -> Response:
        flash = responses.flash(message="User not authenticated", category="warning")
        if request.headers.get("HX-Request") == "true":
            response = responses.htmx_response(redirect=responses.url_for("login_page"), flash=flash)
        else:
            response = responses.html_response(redirect=responses.url_for("login_page"), flash=flash)
        response.delete_cookie(key="access_token", path="/", samesite="lax")
        response.delete_cookie(key="csrf_token", path="/", samesite="lax")
        return response

class UserAccountSuspendedException(HTTPException):
    def __init__(self, message: str = "Your account is suspended, please contact us."):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)

    @staticmethod
    def Handler(request: Request, _: Exception) -> Response:
        flash = responses.flash(message="Your account is suspended, please contact us.", category="warning")
        if request.headers.get("HX-Request") == "true":
            response = responses.htmx_response(redirect=responses.url_for("login_page"), flash=flash)
        else:
            response = responses.html_response(redirect=responses.url_for("login_page"), flash=flash)
        response.delete_cookie(key="access_token", path="/", samesite="lax")
        response.delete_cookie(key="csrf_token", path="/", samesite="lax")
        return response

class NoPermissionsException(HTTPException):
    def __init__(self, detail: str = "Permission denied"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )

    @staticmethod
    def Handler(request: Request, _: Exception) -> Response:
        flash = responses.flash(message="Permission denied", category="error")
        if request.headers.get("HX-Request") == "true":
            response = responses.htmx_response(status=status.HTTP_403_FORBIDDEN, flash=flash)
        else:
            response = responses.html_response(
                template="errors/page.html",
                active_page="", msg="Permission denied", code=status.HTTP_403_FORBIDDEN,
                status=status.HTTP_403_FORBIDDEN, flash=flash
            )
        return response

class BadRequestException(HTTPException):
    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    @staticmethod
    def Handler(request: Request, _: Exception) -> Response:
        flash = responses.flash(message="Bad request", category="error")
        if request.headers.get("HX-Request") == "true":
            response = responses.htmx_response(status=status.HTTP_400_BAD_REQUEST, flash=flash)
        else:
            response = responses.html_response(
                template="errors/page.html",
                active_page="", msg="Bad request", code=status.HTTP_400_BAD_REQUEST,
                status=status.HTTP_400_BAD_REQUEST, flash=flash
            )
        return response

class MethodNotAllowedException(HTTPException):
    def __init__(self, detail: str = "Method not allowed"):
        super().__init__(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail=detail
        )
    @staticmethod
    def Handler(request: Request, _: Exception) -> Response:
        flash = responses.flash(message="Method not allowed", category="error")
        if request.headers.get("HX-Request") == "true":
            response = responses.htmx_response(status=status.HTTP_405_METHOD_NOT_ALLOWED, flash=flash)
        else:
            response = responses.html_response(
                template="errors/page.html",
                active_page="", msg="Method not allowed", code=status.HTTP_405_METHOD_NOT_ALLOWED,
                status=status.HTTP_405_METHOD_NOT_ALLOWED, flash=flash
            )
        return response


def request_validation_exception_handler(
    request: Request,
    exc: fastapi_exc.RequestValidationError,
) -> Response:
    logger.debug(f"Request validation failed: {exc.errors()}")

    message = "Invalid request."

    if request.headers.get("HX-Request") == "true":
        return responses.htmx_response(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            flash=responses.flash(message=message, category="error"),
        )

    return responses.html_response(
        template="errors/page.html",
        active_page="",
        msg=message,
        code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        flash=responses.flash(message=message, category="error"),
        request=request,
    )