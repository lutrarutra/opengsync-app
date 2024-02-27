from typing import TYPE_CHECKING

from flask import Blueprint, url_for, flash, request, abort
from flask_htmx import make_response
from flask_mail import Message
from flask_login import logout_user, login_required

from limbless_db import models
from limbless_db.core.categories import HttpResponse, UserRole
from .... import db, forms, logger, mail, serializer, EMAIL_SENDER

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

auth_htmx = Blueprint("auth_htmx", __name__, url_prefix="/api/auth/")


@auth_htmx.route("login", methods=["POST"])
def login():
    dest = request.args.get("next", "/")
    return forms.LoginForm(request.form).process_request(dest=dest)


@auth_htmx.route("logout", methods=["GET"])
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("Logged out!", "info")

    return make_response(redirect=url_for("index_page"))


@auth_htmx.route("register", methods=["POST"])
def register():
    return forms.RegisterForm(request.form).process_request()


@auth_htmx.route("custom_register/", methods=["POST"])
@login_required
def custom_register():
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.id)
    
    return forms.UserForm(request.form).process_request(user=current_user)
    

@auth_htmx.route("complete_registration/<string:token>", methods=["POST"])
def complete_registration(token: str):
    return forms.CompleteRegistrationForm(request.form).process_request(token=token)


@auth_htmx.route("reset_password_email/<int:user_id>", methods=["GET"])
@login_required
def reset_password_email(user_id: int):
    if (user := db.get_user(user_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)
    
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        return abort(HttpResponse.FORBIDDEN.id)
        
    token = current_user.generate_reset_token(serializer=serializer)
    url = url_for("auth_page.reset_password_page", token=token, _external=True)

    msg = Message(
        "Limbless Reset Password",
        sender=EMAIL_SENDER,
        recipients=[user.email],
        body=f"""Follow the link to reset your password:\n
        <a href='{url}'>{url}</a>
        """
    )
    mail.send(msg)

    flash(f"Password reset email sent to '{user.email}'", "info")
    logger.debug(f"Password reset email sent to '{user.email}'")
    return make_response(
        redirect=url_for("users_page.user_page", user_id=user_id),
    )


@auth_htmx.route("reset_password/<token>", methods=["POST"])
def reset_password(token: str):
    return forms.ResetPasswordForm(request.form).process_request(token=token)
