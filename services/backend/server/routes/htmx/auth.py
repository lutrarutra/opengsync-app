from fastapi import APIRouter, Depends, Request

from opengsync_db import models

from ...core import dependencies, responses
from ...forms import auth as auth_forms

router = APIRouter(prefix="/auth", tags=["auth"])
router.include_router(auth_forms.LoginForm.Router())
router.include_router(auth_forms.RegisterForm.Router())

@router.get("/complete-registration/{token}")
def complete_registration_form(
    form: auth_forms.CompleteRegistrationForm = Depends(auth_forms.CompleteRegistrationForm),
):
    return form.make_response()

@router.post("/complete-registration/{token}")
def complete_registration(response = Depends(auth_forms.CompleteRegistrationForm.process_request)): return response


@router.post("/logout")
def logout(
    request: Request,
    current_user: models.User = Depends(dependencies.require_user),
):
    resp = responses.htmx_response(
        redirect=responses.url_for("login_page"),
        flash=responses.flash("Logged out successfully.", "success"),
    )
    resp.delete_cookie(key="access_token", path="/", samesite="lax")
    resp.delete_cookie(key="csrf_token", path="/", samesite="lax")
    return resp