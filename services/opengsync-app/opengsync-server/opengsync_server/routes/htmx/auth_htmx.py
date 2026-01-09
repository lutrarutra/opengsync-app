from pathlib import Path
from flask import Blueprint, url_for, flash, request, render_template
from flask_htmx import make_response
from flask_login import logout_user

from opengsync_db import models
from opengsync_db.categories import UserRole

from ... import db, forms, logger, mail_handler, serializer
from ...core import wrappers, exceptions, runtime, tokens

auth_htmx = Blueprint("auth_htmx", __name__, url_prefix="/htmx/auth/")


@wrappers.htmx_route(auth_htmx, methods=["GET", "POST"], db=db, login_required=False, limit_exempt=None, limit="20 per minute")
def login(current_user: models.User | None):
    if current_user:
        return make_response(redirect=url_for("dashboard"))
    
    dest = request.args.get("next", None)
    if request.method == "GET":
        return forms.auth.LoginForm().make_response(next=dest)
    
    return forms.auth.LoginForm(formdata=request.form).process_request(dest=dest)


@wrappers.htmx_route(auth_htmx, db=db)
def logout(current_user: models.User):
    user_id = current_user.id
    logout_user()
    num_deleted = runtime.app.delete_user_sessions(user_id)
    logger.info(f"Closed {num_deleted} sessions for user ID: {user_id}")
    runtime.session.clear()
    flash("Logged out!", "info")
    return make_response(redirect=url_for("dashboard"))


@wrappers.htmx_route(auth_htmx, db=db, methods=["GET", "POST"], login_required=False, limit_exempt=None, limit="20 per minute")
def register(current_user: models.User | None):
    if request.method == "GET":
        form = forms.auth.RegisterUserForm(current_user=current_user)
        return form.make_response()
    return forms.auth.RegisterUserForm(current_user=current_user, formdata=request.form).process_request()
    

@wrappers.htmx_route(auth_htmx, db=db, login_required=False, methods=["GET", "POST"], limit_exempt=None, limit="20 per minute")
def complete_registration(token: str):
    if request.method == "GET":
        return forms.auth.CompleteRegistrationForm(token=token).make_response()
        
    return forms.auth.CompleteRegistrationForm(token=token, formdata=request.form).process_request()


@wrappers.htmx_route(auth_htmx, methods=["GET", "POST"], db=db)
def change_password(current_user: models.User, user_id: int):
    if current_user.id != user_id and not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        return forms.auth.ChangePasswordForm(user=user).make_response(user_id=user_id)
    else:
        return forms.auth.ChangePasswordForm(user=user, formdata=request.form).process_request()
    

@wrappers.htmx_route(auth_htmx, db=db, methods=["POST"])
def reset_password_email(current_user: models.User, user_id: int):
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise exceptions.NoPermissionsException()
        
    token = tokens.generate_reset_token(user=user, serializer=serializer)
    link = runtime.url_for("auth_page.reset_password_page", token=token, _external=True)
    style = open(Path(runtime.app.static_folder) / "style/compiled/email.css").read()

    try:
        mail_handler.send_email(
            recipients=user.email,
            subject="OpeNGSync Password Reset",
            body=render_template("email/password-reset.html", recipient=user, link=link, style=style),
            mime_type="html"
        )
    except Exception as e:
        flash("Failed to send password reset email. Please contact administrator.", "error")
        logger.error(f"Failed to send password reset email to '{user.email}':")
        logger.error(e)
        return make_response(redirect=url_for("users_page.user", user_id=user_id))

    flash(f"Password reset email sent to '{user.email}'", "info")
    logger.info(f"Password reset email sent to '{user.email}'")
    return make_response(redirect=url_for("users_page.user", user_id=user_id))


@wrappers.htmx_route(auth_htmx, db=db, methods=["POST"])
def activate_account(current_user: models.User, user_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if user.role != UserRole.DEACTIVATED:
        logger.warning(f"Attempted to activate account for user ID {user_id} but account is not deactivated")
        raise exceptions.BadRequestException("User account is not deactivated")
    
    user.role = UserRole.CLIENT
    db.users.update(user)

    token = tokens.generate_reset_token(user=user, serializer=serializer)
    link = runtime.url_for("auth_page.reset_password_page", token=token, _external=True)
    style = open(Path(runtime.app.static_folder) / "style/compiled/email.css").read()

    try:
        mail_handler.send_email(
            recipients=user.email,
            subject="OpeNGSync Account Activation",
            body=render_template("email/user-activation.html", recipient=user, link=link, style=style),
            mime_type="html"
        )
    except Exception as e:
        flash("Failed to send password reset email. Please contact administrator.", "error")
        logger.error(f"Failed to send password reset email to '{user.email}':")
        logger.error(e)
        return make_response(redirect=url_for("users_page.user", user_id=user_id))

    flash(f"Account activation email sent to '{user.email}'", "info")
    logger.info(f"Account activation email sent to '{user.email}'")
    return make_response(redirect=url_for("users_page.user", user_id=user_id))



@wrappers.htmx_route(auth_htmx, methods=["GET", "POST"], db=db, login_required=False, limit_exempt=None, limit="20 per minute")
def reset_password(token: str):
    if request.method == "GET":
        form = forms.auth.ResetPasswordForm(token=token)
        return form.make_response()
    
    form = forms.auth.ResetPasswordForm(token=token, formdata=request.form)
    return form.process_request()


@wrappers.htmx_route(auth_htmx, methods=["POST"], db=db, login_required=True)
def delete_user_sessions(current_user: models.User, user_id: int):
    if current_user.id != user_id and not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if current_user.id == user_id:
        logout_user()
    
    runtime.app.delete_user_sessions(user_id)
    flash(f"Deleted all sessions for user '{user.email}'", "info")
    logger.info(f"Deleted all sessions for user '{user.id}'")
    return make_response(redirect=url_for("users_page.user", user_id=user_id))
