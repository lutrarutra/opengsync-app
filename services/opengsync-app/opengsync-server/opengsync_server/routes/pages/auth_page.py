from flask import Blueprint, render_template, redirect, request, url_for, flash, abort
from flask_login import current_user

from opengsync_db import models
from opengsync_db.categories import HTTPResponse
from ... import forms, db, logger, serializer

auth_page_bp = Blueprint("auth_page", __name__)


@auth_page_bp.route("/reset_password/<token>", methods=["GET"])
def reset_password_page(token: str):
    reset_password_form = forms.ResetPasswordForm()

    if (data := models.User.verify_reset_token(token=token, serializer=serializer)) is None:
        flash("Token expired or invalid.", "error")
        return redirect(url_for("auth_page.auth_page"))
    
    user_id, email, hash = data
    if (user := db.get_user(user_id)) is None:
        flash("Token expired or invalid.", "error")
        return redirect(url_for("auth_page.auth_page"))
    
    if user.email != email:
        flash("Token expired or invalid.", "error")
        return redirect(url_for("auth_page.auth_page"))
    
    if user.password != hash:
        flash("Token expired or invalid.", "error")
        return redirect(url_for("auth_page.auth_page"))

    return render_template(
        "reset_password_page.html",
        reset_password_form=reset_password_form,
        email=email, token=token
    )


@auth_page_bp.route("/auth")
def auth_page():
    dest = request.args.get("next")

    if current_user.is_authenticated:
        return redirect(url_for("users_page.user_page"))

    return render_template(
        "auth_page.html",
        login_form=forms.LoginForm(),
        register_form=forms.RegisterForm(),
        next=dest
    )


@auth_page_bp.route("/register/<token>")
def register_page(token):
    complete_registration_form = forms.CompleteRegistrationForm()

    if (data := models.User.verify_registration_token(token=token, serializer=serializer)) is None:
        flash("Token expired or invalid.", "warning")
        return redirect(url_for("auth_page.auth_page"))
    
    email, user_role = data
    if (_ := db.get_user_by_email(email)) is not None:
        flash("Email already registered.", "warning")
        return redirect(url_for("auth_page.auth_page"))

    return render_template(
        "register_page.html",
        complete_registration_form=complete_registration_form,
        user_role=user_role,
        email=email, token=token
    )
