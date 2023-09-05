from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import current_user

from ... import forms, models

auth_page_bp = Blueprint("auth_page", __name__)


@auth_page_bp.route("/auth")
def auth_page():
    dest = request.args.get("next")

    if current_user.is_authenticated:
        return redirect(url_for("user_page.user_page"))

    login_form = forms.LoginForm()
    register_form = forms.RegisterForm()

    return render_template(
        "auth_page.html",
        login_form=login_form,
        register_form=register_form,
        next=dest
    )


@auth_page_bp.route("/register/<token>")
def register_page(token):
    register_form = forms.CompleteRegistrationForm()

    email = models.User.verify_registration_token(
        token=token
    )

    if email is None:
        flash("Token expired or invalid.", "warning")
        return redirect(url_for("auth_page.auth_page"))

    register_form.email.data = email

    return render_template(
        "register_page.html",
        register_form=register_form,
        email=email, token=token
    )
