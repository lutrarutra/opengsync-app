from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, status, Request, Response

from . import responses

if TYPE_CHECKING:
    from ..forms import HTMXForm


def generic_exception_handler(request: Request, exc: Exception) -> Response:
    return Response(
        content=f"Internal server error: {str(exc)}",
        status_code=exc.status_code if isinstance(exc, HTTPException) else status.HTTP_500_INTERNAL_SERVER_ERROR
    )

class OpeNGSyncServerException(Exception):
    @staticmethod
    def handler(request: Request, _: Exception) -> Response:
        return generic_exception_handler(request, _)
    

class FormValidationException(HTTPException):
    def __init__(self, form: "HTMXForm", status_code: int = status.HTTP_202_ACCEPTED):
        super().__init__(status_code=status_code)
        self.form = form

class ItemNotFoundException(HTTPException):
    def __init__(self, message: str = "Item not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=message)

class ResourceNotFoundException(HTTPException):
    def __init__(self, resource_name: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_name}' was not found"
        )

class UserNotAuthenticatedException(HTTPException):
    def __init__(self, message: str = "User not authenticated"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)

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

class BadRequestException(HTTPException):
    def __init__(self, detail: str = "Bad request"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )

class MethodNotAllowedException(HTTPException):
    def __init__(self, detail: str = "Method not allowed"):
        super().__init__(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail=detail
        )

class InvalidCredentialsException(OpeNGSyncServerException):
    pass

class StepRequirementNotMetException(OpeNGSyncServerException):
    pass

class DatasetNotLoadedException(StepRequirementNotMetException):
    @staticmethod
    def handler(request: Request, _: Exception) -> Response:
        raise NotImplementedError("DatasetNotLoadedException handler is not implemented yet.")
