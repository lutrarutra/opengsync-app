from flask import Blueprint, render_template, redirect, request, url_for, flash, abort
from flask_login import current_user

from ... import forms, models, db, bcrypt, logger
from ...categories import UserRole, HttpResponse

auth_page_bp = Blueprint("auth_page", __name__)


@auth_page_bp.route("/reset_password/<token>", methods=["GET"])
def reset_password_page(token: str):
    reset_password_form = forms.ResetPasswordForm()

    if (data := models.User.verify_reset_token(token=token)) is None:
        flash("Token expired or invalid.", "warning")
        return redirect(url_for("auth_page.auth_page"))
    
    user_id, email, hash = data
    if (user := db.db_handler.get_user(user_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if user.email != email:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    logger.debug(hash)
    logger.debug(user.password)
    if user.password != hash:
        flash("Token expired or invalid.", "warning")
        return redirect(url_for("auth_page.auth_page"))

    return render_template(
        "reset_password_page.html",
        reset_password_form=reset_password_form,
        user=user, token=token
    )


@auth_page_bp.route("/auth")
def auth_page():
    dest = request.args.get("next")

    if current_user.is_authenticated:
        return redirect(url_for("users_page.user_page"))

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

    if (data := models.User.verify_registration_token(token=token)) is None:
        flash("Token expired or invalid.", "warning")
        return redirect(url_for("auth_page.auth_page"))
    
    email, user_role = data
    if (user := db.db_handler.get_user_by_email(email)) is not None:
        flash("Email already registered.", "warning")
        return redirect(url_for("auth_page.auth_page"))

    return render_template(
        "register_page.html",
        register_form=register_form,
        user_role=user_role,
        email=email, token=token
    )
