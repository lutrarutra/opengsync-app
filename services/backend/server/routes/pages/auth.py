from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/reset-password")
def reset_password_page(token: str):
    return responses.html_response("reset_password_page.html", token=token)

@router.get("/login")
def login_page(
    current_user: models.User | None = Depends(dependencies.get_user)
):
    if current_user:
        return responses.html_response(redirect=responses.url_for("dashboard"))
    
    return responses.html_response("auth_page.html")

@router.get("/complete-registration/{token}")
def complete_registration_page(token: str):
    return responses.html_response("complete_registration_page.html", token=token)