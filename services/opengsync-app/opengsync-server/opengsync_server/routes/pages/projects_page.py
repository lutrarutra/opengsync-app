from flask import Blueprint, render_template, url_for, request

from opengsync_db import models
from opengsync_db.categories import AccessType
from ... import db, forms
from ...core import wrappers, exceptions

projects_page_bp = Blueprint("projects_page", __name__)


@wrappers.page_route(projects_page_bp, db=db, cache_timeout_seconds=360)
def projects():
    return render_template("projects_page.html", form=forms.models.ProjectForm())


@wrappers.page_route(projects_page_bp, "projects", db=db, cache_timeout_seconds=360)
def project(current_user: models.User, project_id: int):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.projects.get_access_type(project, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()

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
