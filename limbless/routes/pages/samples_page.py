from flask import Blueprint, render_template, redirect, request, url_for

samples_page_bp = Blueprint("samples_page", __name__)

from ... import db
from ... import models, forms
from ...core import DBSession

@samples_page_bp.route("/samples")
def samples_page():
    with DBSession(db.db_handler) as session:
        samples = session.get_samples()
        n_pages = int(session.get_num_samples() / 20)

    return render_template(
        "samples_page.html", samples=samples,
        n_pages=n_pages, active_page=0
    )

@samples_page_bp.route("/samples/<sample_id>")
def sample_page(sample_id):
    sample = db.db_handler.get_sample(sample_id)
    if not sample:
        return redirect(url_for("samples_page.samples_page"))
    
    sample_form = forms.SampleForm()

    sample_form.name.data = sample.name
    sample_form.organism.data = sample.organism

    with DBSession(db.db_handler) as session:
        sample = session.get_sample(sample_id)
        libraries = session.get_sample_libraries(sample.id)
        runs = []
        for library in sample.libraries:
            runs.extend(session.get_library_runs(library.id))
        

    return render_template(
        "sample_page.html", sample_form=sample_form, sample=sample,
        libraries=libraries, runs=runs
    )