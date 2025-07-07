from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required, current_user

from limbless_db import db_session
from limbless_db.categories import HTTPResponse
from ... import db, forms

projects_page_bp = Blueprint("projects_page", __name__)


@projects_page_bp.route("/projects")
@db_session(db)
@login_required
def projects_page():
    return render_template("projects_page.html", form=forms.models.ProjectForm())


@projects_page_bp.route("/projects/<int:project_id>")
@db_session(db)
@login_required
def project_page(project_id):
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and project.owner_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=project.group_id) if project.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)

    path_list = [
        ("Projects", url_for("projects_page.projects_page")),
        (f"Project {project_id}", ""),
    ]

    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "user":
            path_list = [
                ("Users", url_for("users_page.users_page")),
                (f"User {id}", url_for("users_page.user_page", user_id=id)),
                (f"Project {project_id}", ""),
            ]
        elif page == "seq_request":
            path_list = [
                ("Requests", url_for("seq_requests_page.seq_requests_page")),
                (f"Request {id}", url_for("seq_requests_page.seq_request_page", seq_request_id=id)),
                (f"Project {project_id}", ""),
            ]

    return render_template(
        "project_page.html", project=project,
        path_list=path_list,
        form=forms.models.ProjectForm(project=project),
    )
