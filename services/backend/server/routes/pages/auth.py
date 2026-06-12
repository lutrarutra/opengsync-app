from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/reset-password")
async def reset_password_page(token: str):
    return await responses.html_response("reset_password_page.html", token=token)

@router.get("/login")
async def login_page(
    current_user: models.User | None = Depends(dependencies.get_user)
):
    if current_user:
        return await responses.html_response(redirect=responses.url_for("dashboard"))
    
    return await responses.html_response("auth_page.html")

@router.get("/complete-registration/{token}")
async def complete_registration_page(token: str):
    return await responses.html_response("complete_registration_page.html", token=token)