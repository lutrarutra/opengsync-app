from typing import TYPE_CHECKING

from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required

from limbless_db import db_session, models
from limbless_db.categories import HTTPResponse, UserRole, AffiliationType

from ... import db, forms, logger  # noqa

if TYPE_CHECKING:
    current_user: models.User = None  # type: ignore
else:
    from flask_login import current_user

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
        elif page == "seq_request":
            path_list = [
                ("Requests", url_for("seq_requests_page.seq_requests_page")),
                (f"Request {id}", url_for("seq_requests_page.seq_request_page", seq_request_id=id)),
                (f"Group {group.id}", ""),
            ]
        elif page == "project":
            path_list = [
                ("Projects", url_for("projects_page.projects_page")),
                (f"Project {id}", url_for("projects_page.project_page", project_id=id)),
                (f"Group {group.id}", ""),
            ]

    affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=group_id)

    can_edit = current_user.role == UserRole.ADMIN or (affiliation is not None and affiliation.affiliation_type == AffiliationType.OWNER)
    can_add_users = current_user.is_insider() or (affiliation is not None and affiliation.affiliation_type in (AffiliationType.OWNER, AffiliationType.MANAGER))
    
    if can_edit:
        group_form = forms.models.GroupForm(group=group)
    else:
        group_form = None

    return render_template("group_page.html", group=group, path_list=path_list, group_form=group_form, can_edit=can_edit, can_add_users=can_add_users)