from flask import Blueprint, render_template, url_for, request

from opengsync_db import models
from opengsync_db.categories import AccessType

from ... import db
from ...core import wrappers, exceptions
samples_page_bp = Blueprint("samples_page", __name__)


@wrappers.page_route(samples_page_bp, db=db, cache_timeout_seconds=360)
def samples():
    return render_template("samples_page.html")


@wrappers.page_route(samples_page_bp, db=db, cache_timeout_seconds=360)
def sample(current_user: models.User, sample_id: int):
    if (sample := db.samples.get(sample_id)) is None:
        raise exceptions.NotFoundException()
        
    if db.samples.get_access_type(sample, current_user) < AccessType.VIEW:
        raise exceptions.NoPermissionsException()

    path_list = [
        ("Samples", url_for("samples_page.samples")),
        (f"Sample {sample_id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries")),
                (f"Library {id}", url_for("libraries_page.library", library_id=id)),
                (f"Sample {sample_id}", ""),
            ]
        elif page == "project":
            path_list = [
                ("Projects", url_for("projects_page.projects")),
                (f"Project {id}", url_for("projects_page.project", project_id=id)),
                (f"Sample {sample_id}", ""),
            ]
        elif page == "seq_request":
            path_list = [
                ("Requests", url_for("seq_requests_page.seq_requests")),
                (f"Request {id}", url_for("seq_requests_page.seq_request", seq_request_id=id)),
                (f"Sample {sample_id}", ""),
            ]

    return render_template("sample_page.html", path_list=path_list, sample=sample)
