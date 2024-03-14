from typing import Optional, TYPE_CHECKING

from flask import Blueprint, render_template, url_for, abort, request
from flask_login import login_required

from limbless_db import models
from limbless_db.categories import HTTPResponse
from ... import db, forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

users_page_bp = Blueprint("users_page", __name__)


@users_page_bp.route("/users")
@login_required
def users_page():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    users, n_pages = db.get_users()

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
            return abort(HTTPResponse.FORBIDDEN.id)
        
    if (user := db.get_user(user_id)) is None:
        return abort(HTTPResponse.FORBIDDEN.id)

    path_list = [
        ("Users", url_for("users_page.users_page")),
        (f"User {user_id}", ""),
    ]

    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries_page")),
                (f"Library {id}", url_for("libraries_page.library_page", library_id=id)),
                (f"User {user_id}", ""),
            ]
        elif page == "project":
            path_list = [
                ("Projects", url_for("projects_page.projects_page")),
                (f"Project {id}", url_for("projects_page.project_page", project_id=id)),
                (f"User {user_id}", ""),
            ]
        elif page == "sample":
            path_list = [
                ("Samples", url_for("samples_page.samples_page")),
                (f"Sample {id}", url_for("samples_page.sample_page", sample_id=id)),
                (f"User {user_id}", ""),
            ]
        elif page == "pool":
            path_list = [
                ("Pools", url_for("pools_page.pools_page")),
                (f"Pool {id}", url_for("pools_page.pool_page", pool_id=id)),
                (f"User {user_id}", ""),
            ]

    projects, _ = db.get_projects(user_id=user_id, limit=None)
    seq_requests, _ = db.get_seq_requests(user_id=user_id, limit=None)
    return render_template(
        "user_page.html", user=user, path_list=path_list,
        projects=projects, seq_requests=seq_requests
    )