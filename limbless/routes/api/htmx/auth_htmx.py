from flask import Blueprint, url_for, render_template, flash, request, abort
from flask_htmx import make_response
from flask_mail import Message
from flask_login import login_user, current_user, logout_user, login_required

from .... import db, forms, logger, models, mail, EMAIL_SENDER
from ....categories import HttpResponse, UserRole

auth_htmx = Blueprint("auth_htmx", __name__, url_prefix="/api/auth/")


@auth_htmx.route("login", methods=["POST"])
def login():
    dest = request.args.get("next", "/")
    login_form = forms.LoginForm()
    validated, login_form = login_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "forms/login.html",
                login_form=login_form,
                next=dest
            ), push_url=False
        )
    
    user, login_form = login_form.login()

    if user is None:
        return make_response(
            render_template(
                "forms/login.html",
                login_form=login_form, next=dest
            ), push_url=False
        )

    login_user(user)
    flash("Logged in.", "success")
    return make_response(redirect=dest)


@auth_htmx.route("logout", methods=["GET"])
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("Logged out!", "info")

    return make_response(
        redirect=url_for("index_page"),
    )


@auth_htmx.route("register", methods=["POST"])
def register():
    register_form = forms.RegisterForm()
    validated, register_form = register_form.custom_validate(db.db_handler)

    if not validated:
        return make_response(
            render_template(
                "forms/register.html",
                register_form=register_form
            ), push_url=False
        )

    email = register_form.email.data.strip()
    token = models.User.generate_registration_token(
        email=email, role=UserRole.CLIENT
    )
    msg = Message(
        "Limbless Registration",
        sender=EMAIL_SENDER,
        recipients=[email],
        body=f"""Click the following link to register:\n
        {url_for("auth_page.register_page", token=token, _external=True)}
        """
    )
    mail.send(msg)

    flash("Email sent. Check your email for registration link.", "info")
    logger.debug(f"Registration email sent to {email}")
    return make_response(
        redirect=url_for("index_page"),
    )


@auth_htmx.route("custom_register/", methods=["POST"])
@login_required
def custom_register():
    if current_user.role_type not in UserRole.insiders:
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    user_form = forms.UserForm()
    validated, user_form = user_form.custom_validate(db.db_handler, current_user)

    if not validated:
        return make_response(
            render_template(
                "forms/user.html",
                user_form=user_form
            ), push_url=False
        )
    
    email = user_form.email.data.strip()
    user_role = UserRole.get(user_form._role_id)

    token = models.User.generate_registration_token(email=email, role=user_role)

    url = url_for("auth_page.register_page", token=token, _external=True)
    msg = Message(
        "Limbless Registration",
        sender=EMAIL_SENDER,
        recipients=[email],
        body=f"""Follow the link to register:\n
        \n
        <a href='{url}'>{url}</a>
        """
    )
    mail.send(msg)

    flash("Email sent. Check your email for registration link.", "info")
    logger.debug(f"Registration email sent to {email}")
    return make_response(
        redirect=url_for("index_page"),
    )


@auth_htmx.route("complete_registration/<token>", methods=["POST"])
def complete_registration(token):
    register_form = forms.CompleteRegistrationForm()
    
    if (data := models.User.verify_registration_token(token=token)) is None:
        flash("Token expired or invalid.", "warning")
        return make_response(
            redirect=url_for("auth_page.auth_page"),
        )
    
    validated, register_form = register_form.custom_validate(db.db_handler)
    email, user_role = data

    if not validated:
        return make_response(
            render_template(
                "forms/complete_register.html",
                register_form=register_form, email=email,
                user_role=user_role, token=token
            ), push_url=False
        )

    user = db.db_handler.create_user(
        email=email,
        password=register_form.password.data,
        first_name=register_form.first_name.data,
        last_name=register_form.last_name.data,
        role=user_role,
    )

    flash("Registration completed!", "success")
    logger.debug(f"Registration completed for {user.email}")
    return make_response(
        redirect=url_for("auth_page.auth_page"),
    )


@auth_htmx.route("reset_password_email/<int:user_id>", methods=["GET"])
@login_required
def reset_password_email(user_id: int):
    if current_user.role_type != UserRole.ADMIN:
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (user := db.db_handler.get_user(user_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
        
    token = user.generate_reset_token()
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
    reset_password_form = forms.ResetPasswordForm()
    if (data := models.User.verify_reset_token(token=token)) is None:
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    validated, reset_password_form = reset_password_form.custom_validate()
    user_id, email, hash = data

    if (user := db.db_handler.get_user(user_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if user.email != email:
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if user.password != hash:
        return abort(HttpResponse.FORBIDDEN.value.id)

    if not validated:
        logger.debug(reset_password_form.errors)
        return make_response(
            render_template(
                "forms/reset_password.html",
                reset_password_form=reset_password_form,
                user=user, token=token
            ), push_url=False
        )

    db.db_handler.update_user(
        user_id=user_id, password=reset_password_form.password.data
    )

    flash("Password changed!", "success")
    logger.debug(f"Password changed for {user.email}")
    return make_response(
        redirect=url_for("auth_page.auth_page"),
    )
