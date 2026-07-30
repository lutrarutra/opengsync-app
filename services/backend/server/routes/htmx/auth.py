from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses
from ... import forms

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/logout")
def logout(
    current_user: models.User = Depends(dependencies.require_user),
):
    resp = responses.htmx_response(
        redirect=responses.url_for("login_page"),
        flash=responses.flash("Logged out successfully.", "success"),
    )
    resp.delete_cookie(key="access_token", path="/", samesite="lax")
    resp.delete_cookie(key="csrf_token", path="/", samesite="lax")
    return resp

router.include_router(forms.auth.LoginForm.Router())
router.include_router(forms.auth.RegisterForm.Router())
router.include_router(forms.auth.ResetPasswordForm.Router())
router.include_router(forms.auth.CompleteRegistrationForm.Router())
router.include_router(forms.auth.ChangePasswordForm.Router())