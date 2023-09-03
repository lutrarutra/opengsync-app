from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import login_required, current_user

runs_page_bp = Blueprint("runs_page", __name__)

from ... import db
from ... import models, forms
from ...core import exceptions
from ...core import DBSession

@runs_page_bp.route("/runs")
@login_required
def runs_page():
    form = forms.RunForm()
    with DBSession(db.db_handler) as session:
        runs = session.get_runs()
        n_pages = int(session.get_num_runs() / 20)

    return render_template(
        "runs_page.html", form=form, runs=runs,
        n_pages=n_pages, page=0
    )

@runs_page_bp.route("/runs/<run_id>", methods=["GET", "POST"])
@login_required
def run_page(run_id):
    with DBSession(db.db_handler) as session:
        run = session.get_run(run_id)
        if not run:
            return redirect("/runs")
        
    run_form = forms.RunForm()
    run_form.lane.data = run.lane
    run_form.r1_cycles.data = run.r1_cycles
    run_form.r2_cycles.data = run.r2_cycles
    run_form.i1_cycles.data = run.i1_cycles
    run_form.i2_cycles.data = run.i2_cycles

    library_form = forms.LibraryForm()

    with DBSession(db.db_handler) as session:
        run = session.get_run(run_id)
        run.libraries = session.get_run_libraries(run_id)
        for library in run.libraries:
            library.samples = session.get_library_samples(library.id)
            library._num_samples = len(library.samples)

    return render_template(
        "run_page.html", run=run,
        library_form=library_form,
        run_form=run_form,
        search_form=forms.SearchForm()
    )
