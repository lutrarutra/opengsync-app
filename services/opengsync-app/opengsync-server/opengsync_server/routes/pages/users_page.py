from flask import Blueprint, render_template, url_for, request

from opengsync_db import models

from ... import db, logger  # noqa: F401
from ...core import wrappers, exceptions

users_page_bp = Blueprint("users_page", __name__)


@wrappers.page_route(users_page_bp, db=db, cache_timeout_seconds=360)
def users(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    return render_template("users_page.html")


@wrappers.page_route(users_page_bp, route="users", db=db, cache_timeout_seconds=360)
def user(current_user: models.User, user_id: int | None = None):
    if user_id is None:
        user_id = current_user.id

    if not current_user.is_insider():
        if user_id != current_user.id:
            raise exceptions.NoPermissionsException()
        
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NoPermissionsException()

    path_list = [
        ("Users", url_for("users_page.users")),
        (f"User {user_id}", ""),
    ]

    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries")),
                (f"Library {id}", url_for("libraries_page.library", library_id=id)),
                (f"User {user_id}", ""),
            ]
        elif page == "project":
            path_list = [
                ("Projects", url_for("projects_page.projects")),
                (f"Project {id}", url_for("projects_page.project", project_id=id)),
                (f"User {user_id}", ""),
            ]
        elif page == "sample":
            path_list = [
                ("Samples", url_for("samples_page.samples")),
                (f"Sample {id}", url_for("samples_page.sample", sample_id=id)),
                (f"User {user_id}", ""),
            ]
        elif page == "pool":
            path_list = [
                ("Pools", url_for("pools_page.pools")),
                (f"Pool {id}", url_for("pools_page.pool", pool_id=id)),
                (f"User {user_id}", ""),
            ]
        elif page == "group":
            path_list = [
                ("Groups", url_for("groups_page.groups")),
                (f"Group {id}", url_for("groups_page.group", group_id=id)),
                (f"User {user_id}", ""),
            ]
        elif page == "lab_prep":
            path_list = [
                ("Lab Preps", url_for("lab_preps_page.lab_preps")),
                (f"Lab Prep {id}", url_for("lab_preps_page.lab_prep", lab_prep_id=id)),
                (f"User {user_id}", ""),
            ]
        elif page == "experiment":
            path_list = [
                ("Experiments", url_for("experiments_page.experiments")),
                (f"Experiment {id}", url_for("experiments_page.experiment", experiment_id=id)),
                (f"User {user_id}", ""),
            ]
            
    projects, _ = db.projects.find(user_id=user_id, limit=None)
    seq_requests, _ = db.seq_requests.find(user_id=user_id, limit=None)
    return render_template(
        "user_page.html", user=user, path_list=path_list,
        projects=projects, seq_requests=seq_requests
    )