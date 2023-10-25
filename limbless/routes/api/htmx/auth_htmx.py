from flask import Blueprint, url_for, render_template, flash, request
from flask_htmx import make_response
from flask_mail import Message
from flask_login import login_user, current_user, logout_user

from .... import db, forms, logger, models, bcrypt, mail, EMAIL_SENDER
from .... import categories

auth_htmx = Blueprint("auth_htmx", __name__, url_prefix="/api/auth/")


@auth_htmx.route("/login", methods=["POST"])
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


@auth_htmx.route("/logout", methods=["GET"])
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("Logged out!", "info")

    return make_response(
        redirect=url_for("index_page"),
    )


@auth_htmx.route("/register", methods=["POST"])
def register():
    register_form = forms.RegisterForm()

    if not register_form.validate_on_submit():
        template = render_template(
            "forms/register.html",
            register_form=register_form
        )
        return make_response(
            template, push_url=False
        )

    email = register_form.email.data
    token = models.User.generate_registration_token(
        email=email
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
    logger.debug(f"Registration email sent to {register_form.email.data}")
    return make_response(
        redirect=url_for("index_page"),
    )


@auth_htmx.route("/complete_registration/<token>", methods=["POST"])
def complete_registration(token):
    register_form = forms.CompleteRegistrationForm()

    email = models.User.verify_registration_token(
        token=token
    )
    if email is None:
        flash("Token expired or invalid.", "warning")
        return make_response(
            redirect=url_for("auth_page.auth_page"),
        )

    register_form.email.data = email

    if not register_form.validate_on_submit():
        logger.debug(register_form.errors)
        template = render_template(
            "forms/complete_register.html",
            register_form=register_form
        )
        return make_response(
            template, push_url=False
        )

    user = db.db_handler.create_user(
        email=register_form.email.data,
        password=register_form.password.data,
        first_name=register_form.first_name.data,
        last_name=register_form.last_name.data,
        role=categories.UserRole.CLIENT,
    )

    flash("Registration completed!", "success")
    logger.debug(f"Registration completed for {user.email}")
    return make_response(
        redirect=url_for("auth_page.auth_page"),
    )
