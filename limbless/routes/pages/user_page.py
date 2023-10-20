from typing import Optional

from flask import Blueprint, render_template, redirect, url_for, abort
from flask_login import current_user, login_required

from ... import logger, db
from ...categories import UserRole, HttpResponse

user_page_bp = Blueprint("user_page", __name__)

@user_page_bp.route("/users")
@login_required
def users_page():
    if current_user.role_type not in [UserRole.ADMIN, UserRole.TECHNICIAN, UserRole.BIOINFORMATICIAN]:
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    users = db.db_handler.get_users(limit=20)
    n_pages = int(db.db_handler.get_num_users() / 20)

    return render_template(
        "users_page.html",
        users=users,
        page=0, n_pages=n_pages,
        current_sort="id", current_sort_order="inc"
    )


@user_page_bp.route("/user", defaults={"user_id": None})
@user_page_bp.route("/user/<int:user_id>")
@login_required
def user_page(user_id: Optional[int]):
    if user_id is None:
        user_id = current_user.id

    if current_user.role_type == UserRole.CLIENT:
        if user_id != current_user.id:
            return abort(HttpResponse.FORBIDDEN.value.id)
        
    if (user := db.db_handler.get_user(user_id)) is None:
        return abort(HttpResponse.FORBIDDEN.value.id)

    return render_template(
        "user_page.html", user=user
    )