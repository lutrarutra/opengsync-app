from typing import TYPE_CHECKING

from flask import Blueprint, url_for, flash, request, abort
from flask_htmx import make_response
from flask_mail import Message
from flask_login import logout_user, login_required

from opengsync_db import models, db_session
from opengsync_db.categories import HTTPResponse, UserRole
from .... import db, forms, logger, mail, serializer, EMAIL_SENDER, htmx_route

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

auth_htmx = Blueprint("auth_htmx", __name__, url_prefix="/api/hmtx/auth/")


@htmx_route(auth_htmx, methods=["GET", "POST"], db=db, login_required=False)
def login():
    if current_user.is_authenticated:
        return make_response(redirect=url_for("dashboard"))
    
    dest = request.args.get("next", "/")
    if request.method == "GET":
        return forms.auth.LoginForm().make_response(next=dest)
    
    return forms.auth.LoginForm(formdata=request.form).process_request(dest=dest)


@htmx_route(auth_htmx, db=db, login_required=False)
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("Logged out!", "info")

    return make_response(redirect=url_for("dashboard"))


@htmx_route(auth_htmx, db=db, login_required=False, methods=["GET", "POST"])
def register():
    user = None
    if current_user.is_authenticated:
        if current_user.is_admin():
            user = current_user

    if request.method == "GET":
        return forms.auth.RegisterUserForm(user=user).make_response()
    return forms.auth.RegisterUserForm(user=user, formdata=request.form).process_request()
    

@htmx_route(auth_htmx, db=db, login_required=False, methods=["POST"])
def complete_registration(token: str):
    return forms.auth.CompleteRegistrationForm(request.form).process_request(token=token)


@htmx_route(auth_htmx, methods=["GET", "POST"], db=db)
def change_password(user_id: int):
    if current_user.id != user_id and not current_user.is_admin():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (user := db.get_user(user_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if request.method == "GET":
        return forms.auth.ChangePasswordForm(user=user).make_response(user_id=user_id)
    else:
        return forms.auth.ChangePasswordForm(user=user, formdata=request.form).process_request()
    

@htmx_route(auth_htmx, db=db)
def reset_password_email(user_id: int):
    if (user := db.get_user(user_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        return abort(HTTPResponse.FORBIDDEN.id)
        
    token = user.generate_reset_token(serializer=serializer)
    url = url_for("auth_page.reset_password_page", token=token, _external=True)

    msg = Message(
        "opengsync Reset Password",
        sender=EMAIL_SENDER,
        recipients=[user.email],
        body=f"""Follow the link to reset your password:\n
        <a href='{url}'>{url}</a>
        """
    )
    mail.send(msg)

    flash(f"Password reset email sent to '{user.email}'", "info")
    logger.info(f"Password reset email sent to '{user.email}'")
    return make_response(
        redirect=url_for("users_page.user", user_id=user_id),
    )