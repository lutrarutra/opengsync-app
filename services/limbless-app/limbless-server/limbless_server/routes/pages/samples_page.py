from typing import TYPE_CHECKING

from flask import Blueprint, render_template, url_for, abort, request
from flask_login import login_required

from limbless_db import DBSession
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
    with DBSession(db) as session:
        if not current_user.is_insider():
            samples, n_pages = session.get_samples(user_id=current_user.id, sort_by="id", descending=True)
        else:
            samples, n_pages = session.get_samples(user_id=None, sort_by="id", descending=True)

    return render_template(
        "samples_page.html", samples=samples,
        samples_n_pages=n_pages, samples_active_page=0,
        current_sort="id", current_sort_order="desc"
    )


@samples_page_bp.route("/samples/<sample_id>")
@login_required
def sample_page(sample_id):
    with DBSession(db) as session:
        if (sample := session.get_sample(sample_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)

        if not current_user.is_insider() and sample.owner_id != current_user.id:
            return abort(HTTPResponse.FORBIDDEN.id)

        sample_form = forms.models.SampleForm(sample=sample)
        sample.project
        libraries = sample.libraries
        seq_requests, seq_requests_n_pages = session.get_seq_requests(sample_id=sample_id, sort_by="id", descending=True)

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

    return render_template(
        "sample_page.html", sample_form=sample_form,
        path_list=path_list, sample=sample,
        libraries=libraries,
        seq_requests=seq_requests,
        seq_requests_n_pages=seq_requests_n_pages
    )
