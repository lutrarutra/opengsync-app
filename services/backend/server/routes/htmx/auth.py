from fastapi import APIRouter, Depends, Request

from opengsync_db import models

from ...core import dependencies, responses
from ...forms import auth as auth_forms

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def get_login_form(
    form: auth_forms.LoginForm = Depends(auth_forms.LoginForm),
    current_user: models.User | None = Depends(dependencies.get_user),
):
    if current_user:
        return responses.htmx_response(redirect=responses.url_for("dashboard"))

    return await form.make_response()

    
@router.post("/login")
async def login_user(response = Depends(auth_forms.LoginForm.process_request)): return response

@router.get("/register")
async def get_register_form(
    form: auth_forms.RegisterForm = Depends(auth_forms.RegisterForm),
    current_user: models.User | None = Depends(dependencies.get_user),
):
    if current_user:
        return responses.htmx_response(redirect=responses.url_for("dashboard"))

    return await form.make_response()

@router.post("/register")
async def register_user(
    response = Depends(auth_forms.RegisterForm.process_request),
):
    return response

@router.get("/complete-registration/{token}")
async def complete_registration_form(
    form: auth_forms.CompleteRegistrationForm = Depends(auth_forms.CompleteRegistrationForm),
):
    return await form.make_response()

@router.post("/complete-registration/{token}")
async def complete_registration(response = Depends(auth_forms.CompleteRegistrationForm.process_request)): return response


@router.post("/logout")
async def logout(
    request: Request,
    current_user: models.User = Depends(dependencies.require_user),
):
    resp = await responses.htmx_response(
        redirect=responses.url_for("login_page"),
        flash=responses.flash("Logged out successfully.", "success"),
    )
    resp.delete_cookie(key="access_token", path="/", samesite="lax")
    resp.delete_cookie(key="csrf_token", path="/", samesite="lax")
    return resp