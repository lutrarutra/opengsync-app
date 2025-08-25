from flask import Blueprint, url_for, flash, request
from flask_htmx import make_response
from flask_mail import Message
from flask_login import logout_user

from opengsync_db import models
from opengsync_db.categories import UserRole

from .... import db, forms, logger, mail, serializer, EMAIL_SENDER
from ....core import wrappers, exceptions

auth_htmx = Blueprint("auth_htmx", __name__, url_prefix="/api/hmtx/auth/")


@wrappers.htmx_route(auth_htmx, methods=["GET", "POST"], db=db, login_required=False)
def login(current_user: models.User | None):
    if current_user:
        return make_response(redirect=url_for("dashboard"))
    
    dest = request.args.get("next", "/")
    if request.method == "GET":
        return forms.auth.LoginForm().make_response(next=dest)
    
    return forms.auth.LoginForm(formdata=request.form).process_request(dest=dest)


@wrappers.htmx_route(auth_htmx, db=db)
def logout(current_user: models.User | None):
    if current_user and current_user.is_authenticated:
        logout_user()
        flash("Logged out!", "info")

    return make_response(redirect=url_for("dashboard"))


@wrappers.htmx_route(auth_htmx, db=db, methods=["GET", "POST"], login_required=False)
def register(current_user: models.User | None):
    if request.method == "GET":
        return forms.auth.RegisterUserForm().make_response()
    return forms.auth.RegisterUserForm(formdata=request.form).process_request(user=current_user)
    

@wrappers.htmx_route(auth_htmx, db=db, login_required=False, methods=["POST"])
def complete_registration(token: str):
    return forms.auth.CompleteRegistrationForm(request.form).process_request(token=token)


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
    

@wrappers.htmx_route(auth_htmx, db=db)
def reset_password_email(current_user: models.User, user_id: int):
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise exceptions.NoPermissionsException()
        
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