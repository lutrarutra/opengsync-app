from typing import Optional

from flask import Blueprint, render_template, redirect, url_for, abort
from flask_login import current_user, login_required

from ... import logger, db, forms
from ...categories import UserRole, HttpResponse

users_page_bp = Blueprint("users_page", __name__)


@users_page_bp.route("/users")
@login_required
def users_page():
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    users = db.db_handler.get_users(limit=20)
    n_pages = int(db.db_handler.get_num_users() / 20)

    return render_template(
        "users_page.html",
        users=users,
        page=0, n_pages=n_pages, user_form=forms.UserForm(),
        current_sort="id", current_sort_order="asc"
    )


@users_page_bp.route("/user", defaults={"user_id": None})
@users_page_bp.route("/user/<int:user_id>")
@login_required
def user_page(user_id: Optional[int]):
    if user_id is None:
        user_id = current_user.id

    if not current_user.is_insider():
        if user_id != current_user.id:
            return abort(HttpResponse.FORBIDDEN.value.id)
        
    if (user := db.db_handler.get_user(user_id)) is None:
        return abort(HttpResponse.FORBIDDEN.value.id)

    path_list = [
        ("Users", url_for("users_page.users_page")),
        (f"{user_id}", ""),
    ]

    projects, _ = db.db_handler.get_projects(user_id=user_id, limit=None)
    seq_requests, _ = db.db_handler.get_seq_requests(user_id=user_id, limit=None)
    return render_template(
        "user_page.html", user=user, path_list=path_list,
        projects=projects, seq_requests=seq_requests
    )