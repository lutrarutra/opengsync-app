from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required, current_user

from limbless_db import db_session
from limbless_db.categories import HTTPResponse
from ... import db, forms

groups_page_bp = Blueprint("groups_page", __name__)


@groups_page_bp.route("/groups")
@login_required
def groups_page():
    group_form = forms.models.GroupForm()
    return render_template("groups_page.html", group_form=group_form)


@groups_page_bp.route("/groups/<int:group_id>")
@db_session(db)
@login_required
def group_page(group_id: int):
    if (group := db.get_group(group_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    path_list = [
        ("Groups", url_for("groups_page.groups_page")),
        (f"Group {group.id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "user":
            path_list = [
                ("Users", url_for("users_page.users_page")),
                (f"User {id}", url_for("users_page.user_page", user_id=id)),
                (f"Group {group.id}", ""),
            ]
        
    return render_template("group_page.html", group=group, path_list=path_list)