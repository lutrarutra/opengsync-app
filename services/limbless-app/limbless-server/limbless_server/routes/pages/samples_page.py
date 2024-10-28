from typing import TYPE_CHECKING

from flask import Blueprint, render_template, url_for, abort, request
from flask_login import login_required

from limbless_db import db_session
from limbless_db.models import User
from limbless_db.categories import HTTPResponse
from ... import db, forms

if TYPE_CHECKING:
    current_user: User = None   # type: ignore
else:
    from flask_login import current_user

samples_page_bp = Blueprint("samples_page", __name__)


@samples_page_bp.route("/samples")
@login_required
def samples_page():
    return render_template("samples_page.html")


@samples_page_bp.route("/samples/<int:sample_id>")
@db_session(db)
@login_required
def sample_page(sample_id):
    if (sample := db.get_sample(sample_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if not current_user.is_insider() and sample.owner_id != current_user.id:
        affiliation = db.get_user_sample_access_type(user_id=current_user.id, sample_id=sample.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    is_editable = sample.is_editable()
    sample_form = forms.models.SampleForm(sample=sample)

    path_list = [
        ("Samples", url_for("samples_page.samples_page")),
        (f"Sample {sample_id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries_page")),
                (f"Library {id}", url_for("libraries_page.library_page", library_id=id)),
                (f"Sample {sample_id}", ""),
            ]
        elif page == "project":
            path_list = [
                ("Projects", url_for("projects_page.projects_page")),
                (f"Project {id}", url_for("projects_page.project_page", project_id=id)),
                (f"Sample {sample_id}", ""),
            ]
        elif page == "seq_request":
            path_list = [
                ("Requests", url_for("seq_requests_page.seq_requests_page")),
                (f"Request {id}", url_for("seq_requests_page.seq_request_page", seq_request_id=id)),
                (f"Sample {sample_id}", ""),
            ]

    return render_template(
        "sample_page.html", sample_form=sample_form,
        path_list=path_list, sample=sample,
        is_editable=is_editable
    )
