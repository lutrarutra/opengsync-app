from typing import TYPE_CHECKING

from flask import Blueprint, render_template, url_for, abort, request

from opengsync_db.models import User
from opengsync_db.categories import HTTPResponse
from ... import db, forms, page_route

if TYPE_CHECKING:
    current_user: User = None   # type: ignore
else:
    from flask_login import current_user

samples_page_bp = Blueprint("samples_page", __name__)


@page_route(samples_page_bp, db=db)
def samples():
    return render_template("samples_page.html")


@page_route(samples_page_bp, db=db)
def sample(sample_id):
    if (sample := db.get_sample(sample_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if not current_user.is_insider() and sample.owner_id != current_user.id:
        affiliation = db.get_user_sample_access_type(user_id=current_user.id, sample_id=sample.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    is_editable = sample.is_editable()
    sample_form = forms.models.SampleForm(sample=sample)

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

    return render_template(
        "sample_page.html", sample_form=sample_form,
        path_list=path_list, sample=sample,
        is_editable=is_editable
    )
