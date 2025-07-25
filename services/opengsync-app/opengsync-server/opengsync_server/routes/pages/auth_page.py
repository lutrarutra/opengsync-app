from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import current_user

from opengsync_db import models
from ... import forms, db, logger, serializer, page_route  # noqa

auth_page_bp = Blueprint("auth_page", __name__)


@page_route(auth_page_bp, db=db, login_required=False)
def reset_password(token: str):
    if (data := models.User.verify_reset_token(token=token, serializer=serializer)) is None:
        flash("Token expired or invalid.", "error")
        return redirect(url_for("auth_page.auth"))
    
    user_id, email, hash = data
    if (user := db.get_user(user_id)) is None:
        flash("Token expired or invalid.", "error")
        return redirect(url_for("auth_page.auth"))
    
    if user.email != email:
        flash("Token expired or invalid.", "error")
        return redirect(url_for("auth_page.auth"))
    
    if user.password != hash:
        flash("Token expired or invalid.", "error")
        return redirect(url_for("auth_page.auth"))

    return render_template(
        "reset_password_page.html",
        email=email, token=token
    )


@page_route(auth_page_bp, db=db, login_required=False)
def auth():
    dest = request.args.get("next", "/")
    if current_user.is_authenticated:
        return redirect(url_for("users_page.user"))

    return render_template("auth_page.html", next=dest)


@page_route(auth_page_bp, db=db, login_required=False)
def register(token: str):
    complete_registration_form = forms.auth.CompleteRegistrationForm()

    if (data := models.User.verify_registration_token(token=token, serializer=serializer)) is None:
        flash("Token expired or invalid.", "warning")
        return redirect(url_for("auth_page.auth"))
    
    email, user_role = data
    if (_ := db.get_user_by_email(email)) is not None:
        flash("Email already registered.", "warning")
        return redirect(url_for("auth_page.auth"))

    return render_template(
        "register_page.html",
        complete_registration_form=complete_registration_form,
        user_role=user_role,
        email=email, token=token
    )
