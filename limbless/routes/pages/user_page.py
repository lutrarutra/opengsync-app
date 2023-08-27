from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_bcrypt import Bcrypt
from flask_login import current_user

user_page_bp = Blueprint("user_page", __name__)

from ... import db, forms, models
from ...core import DBSession

@user_page_bp.route("/user")
def user_page():
    if not current_user.is_authenticated:
        return redirect(url_for("auth_page.auth_page"))
    
    return render_template(
        "user_page.html"
    )