from typing import TYPE_CHECKING

from flask import Blueprint, render_template, redirect, url_for, abort, request
from flask_login import login_required

from ... import db, forms, logger, PAGE_LIMIT
from ...core import DBSession
from ...categories import UserRole, HttpResponse
from ...models import User

if TYPE_CHECKING:
    current_user: User = None
else:
    from flask_login import current_user

samples_page_bp = Blueprint("samples_page", __name__)


@samples_page_bp.route("/samples")
@login_required
def samples_page():
    with DBSession(db.db_handler) as session:
        if not current_user.is_insider():
            samples, n_pages = session.get_samples(limit=PAGE_LIMIT, user_id=current_user.id, sort_by="id", descending=True)
        else:
            samples, n_pages = session.get_samples(limit=PAGE_LIMIT, user_id=None, sort_by="id", descending=True)

    return render_template(
        "samples_page.html", samples=samples,
        n_pages=n_pages, active_page=0,
        current_sort="id", current_sort_order="desc"
    )


@samples_page_bp.route("/samples/<sample_id>")
@login_required
def sample_page(sample_id):
    with DBSession(db.db_handler) as session:
        if (sample := session.get_sample(sample_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)

        access = session.get_user_sample_access(current_user.id, sample_id)
        if access is None:
            return abort(HttpResponse.FORBIDDEN.value.id)

    sample_form = forms.SampleForm()
    sample_form.name.data = sample.name
    sample_form.organism.data = sample.organism.tax_id

    with DBSession(db.db_handler) as session:
        sample = session.get_sample(sample_id)
        libraries = session.get_sample_libraries(sample.id)
        sample.libraries = libraries

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
        path_list=path_list, sample=sample, libraries=libraries,
        selected_organism=sample.organism
    )
