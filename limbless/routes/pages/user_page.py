from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

user_page_bp = Blueprint("user_page", __name__)


@user_page_bp.route("/user")
def user_page():
    if not current_user.is_authenticated:
        return redirect(url_for("auth_page.auth_page"))

    return render_template(
        "user_page.html"
    )
