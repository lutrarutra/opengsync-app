from flask import Blueprint, render_template, abort, url_for, request

from opengsync_db import models
from opengsync_db.categories import HTTPResponse
from ... import db, forms
from ...core import wrappers
projects_page_bp = Blueprint("projects_page", __name__)


@wrappers.page_route(projects_page_bp, db=db)
def projects():
    return render_template("projects_page.html", form=forms.models.ProjectForm())


@wrappers.page_route(projects_page_bp, db=db)
def project(current_user: models.User, project_id: int):
    if (project := db.projects.get(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and project.owner_id != current_user.id:
        affiliation = db.groups.get_user_affiliation(user_id=current_user.id, group_id=project.group_id) if project.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)

    path_list = [
        ("Projects", url_for("projects_page.projects")),
        (f"Project {project_id}", ""),
    ]

    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "user":
            path_list = [
                ("Users", url_for("users_page.users")),
                (f"User {id}", url_for("users_page.user", user_id=id)),
                (f"Project {project_id}", ""),
            ]
        elif page == "seq_request":
            path_list = [
                ("Requests", url_for("seq_requests_page.seq_requests")),
                (f"Request {id}", url_for("seq_requests_page.seq_request", seq_request_id=id)),
                (f"Project {project_id}", ""),
            ]

    return render_template(
        "project_page.html", project=project,
        path_list=path_list,
        form=forms.models.ProjectForm(project=project),
    )
