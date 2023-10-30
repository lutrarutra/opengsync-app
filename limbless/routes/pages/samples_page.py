from flask import Blueprint, render_template, redirect, url_for, abort
from flask_login import login_required, current_user

from ... import db, forms, logger
from ...core import DBSession
from ...categories import UserRole, HttpResponse

samples_page_bp = Blueprint("samples_page", __name__)


@samples_page_bp.route("/samples")
@login_required
def samples_page():
    with DBSession(db.db_handler) as session:
        if current_user.role_type == UserRole.CLIENT:
            samples, n_pages = session.get_samples(limit=20, user_id=current_user.id, sort_by="id", reversed=True)
        else:
            samples, n_pages = session.get_samples(limit=20, user_id=None, sort_by="id", reversed=True)

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
        runs = []
        for library in sample.libraries:
            runs.extend(session.get_library_runs(library.id))

    return render_template(
        "sample_page.html", sample_form=sample_form,
        sample=sample, libraries=libraries,
        runs=runs, selected_organism=sample.organism
    )
