from flask import Blueprint, render_template, url_for, request

from opengsync_db import models, queries as Q
from opengsync_db.categories import AccessLevel

from ... import db
from ...core import wrappers, exceptions
samples_page_bp = Blueprint("samples_page", __name__)


@wrappers.page_route(samples_page_bp, db=db, cache_timeout_seconds=360)
def samples():
    return render_template("samples_page.html", title="Samples")


@wrappers.page_route(samples_page_bp, "samples", db=db, cache_timeout_seconds=360)
def sample(current_user: models.User, sample_id: int):
    if (sample := db.session.first(Q.sample.select(id=sample_id))) is None:
        raise exceptions.NotFoundException()
        
    if db.session.get_access_level(Q.sample.permissions(sample.id, current_user.id)) < AccessLevel.READ:
        raise exceptions.NoPermissionsException()

    path_list = [
        ("Samples", url_for("sample_pages")),
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
                ("Projects", url_for("project_pages")),
                (f"Project {id}", url_for("project_page", project_id=id)),
                (f"Sample {sample_id}", ""),
            ]
        elif page == "seq_request":
            path_list = [
                ("Requests", url_for("seq_request_pages")),
                (f"Request {id}", url_for("seq_request_page", seq_request_id=id)),
                (f"Sample {sample_id}", ""),
            ]

    return render_template("sample_page.html", path_list=path_list, sample=sample, title=f"Sample: {sample.name}")
