from fastapi import APIRouter, Depends, Response
from loguru import logger

from opengsync_db import models, categories as C, queries as Q, SyncSession

from ...core import dependencies, responses, mailer, secrets, exceptions as exc, redis as rds
from ... import forms

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(dependencies.audit_log)])

@router.post("/logout")
def logout(
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
    r: rds.RedisClient = Depends(dependencies.redis),
):
    if current_user.role == C.UserRole.TEMPORARY:
        current_user.role = C.UserRole.DEACTIVATED
        session.save(current_user)
        r.delete(f"user:{current_user.id}")

    resp = responses.htmx_response(
        redirect=responses.url_for("login_page"),
        flash=responses.flash("Logged out successfully.", "success"),
    )
    resp.delete_cookie(key="access_token", path="/", samesite="lax")
    resp.delete_cookie(key="csrf_token", path="/", samesite="lax")
    return resp



@router.post("/{user_id}/reset-password")
def send_reset_password_email(
    user_id: int,
    current_user: models.User = Depends(dependencies.require_user),
    access_level: C.AccessLevel = Depends(dependencies.user_permissions),
    session: SyncSession = Depends(dependencies.db_session),
    email: mailer.Mailer = Depends(dependencies.mail_client),
):
    if current_user.id != user_id and access_level < C.AccessLevel.ADMIN:
        raise exc.NoPermissionsException("You do not have permission to change this user's password.")
    
    user = session.get_one(Q.user.select(id=user_id))
        
    token = secrets.create_password_reset_token(user_id=user.id)
    link = responses.url_for("reset_password_page", token=token)
    email.send_password_reset(recipient_email=user.email, reset_link=link)

    return responses.htmx_response(
        redirect=responses.url_for("login_page"),
        flash=responses.flash("Password reset email sent!", "success"),
    )

@router.post("/{user_id}/activate")
def activate_user(
    user_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
    email: mailer.Mailer = Depends(dependencies.mail_client),
):
    
    user = session.get_one(Q.user.select(id=user_id))

    if user.role != C.UserRole.DEACTIVATED:
        raise exc.BadRequestException("User is already active.")
    
    user.role = C.UserRole.CLIENT

    token = secrets.create_password_reset_token(user_id=user.id)
    link = responses.url_for("reset_password_page", token=token)
    email.send_password_reset(recipient_email=user.email, reset_link=link)

    return responses.htmx_response(
        redirect=responses.url_for("login_page"),
        flash=responses.flash("Check your email!", "success"),
    )
    

@router.post("/{user_id}/start-user-session")
def start_user_session(
    user_id: int,
    response: Response,
    current_user: models.User = Depends(dependencies.require_admin),
    session: SyncSession = Depends(dependencies.db_session),
    r: rds.RedisClient = Depends(dependencies.redis),
):
    user = session.get_one(Q.user.select(id=user_id))
    logger.info(f"Admin {current_user.email} started session for user '{user.email}'")

    if user.role == C.UserRole.DEACTIVATED:
        user.role = C.UserRole.TEMPORARY
        session.save(user)
        r.delete(f"user:{user.id}")
    
    response.delete_cookie(key="csrf_token", path="/", samesite="lax")
    response.set_cookie(
        key="access_token",
        value=secrets.create_login_token(user),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,  # 7 days
    )
    return responses.htmx_response(
        redirect=responses.url_for("dashboard"), response=response,
        flash=responses.flash(message="User session started.", category="success")
    )

router.include_router(forms.auth.LoginForm.Router())
router.include_router(forms.auth.RegisterForm.Router())
router.include_router(forms.auth.ResetPasswordForm.Router())
router.include_router(forms.auth.CompleteRegistrationForm.Router())
router.include_router(forms.auth.ChangePasswordForm.Router())