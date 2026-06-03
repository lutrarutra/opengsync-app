from flask import Blueprint, render_template, url_for, request

from opengsync_db import models, queries as Q
from opengsync_db.categories import AccessLevel

from ... import db, logger
from ...core import wrappers, exceptions

projects_page_bp = Blueprint("projects_page", __name__)


@wrappers.page_route(projects_page_bp, db=db, cache_timeout_seconds=360)
def projects():
    return render_template("projects_page.html", title="Projects")


@wrappers.page_route(projects_page_bp, "projects", db=db, cache_timeout_seconds=360)
def project(current_user: models.User, project_id: int):
    if (project := db.session.first(Q.project.select(id=project_id))) is None:
        raise exceptions.NotFoundException()
    
    access_level = db.session.get_access_level(Q.project.permissions(project.id, current_user.id))
    if access_level < AccessLevel.READ:
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
                ("Requests", url_for("seq_request_pages")),
                (f"Request {id}", url_for("seq_request_page", seq_request_id=id)),
                (f"Project {project_id}", ""),
            ]

    return render_template(
        "project_page.html", project=project,
        path_list=path_list, title=f"{project.identifier or f'PRJ#{project.id:04d}'}"
    )
