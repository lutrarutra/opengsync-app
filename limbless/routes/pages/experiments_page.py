from flask import Blueprint, render_template, redirect, request, url_for
from sqlmodel import select, Session

experiments_page_bp = Blueprint("experiments_page", __name__)

from ... import db
from ... import models, forms
from ...core.DBSession import DBSession

@experiments_page_bp.route("/experiments")
def experiments_page():
    experiment_form = forms.ExperimentForm()

    with DBSession(db.db_handler) as session:
        experiments = session.get_experiments()
        n_pages = int(session.get_num_experiments() / 20)

    return render_template(
        "experiments_page.html", experiment_form=experiment_form,
        experiments=experiments,
        n_pages=n_pages, active_page=0
    )

@experiments_page_bp.route("/experiments/<experiment_id>")
def experiment_page(experiment_id):
    experiment = db.db_handler.get_experiment(experiment_id)
    if not experiment:
        return redirect(url_for("experiments_page.experiments_page"))
        
    with DBSession(db.db_handler) as session:
        runs = session.get_experiment_data(experiment_id)
        for run in runs:
            run._num_samples = 0
            for library in run.libraries:
                run._num_samples += len(library.samples)

    run_form = forms.RunForm()
    lanes = [run.lane for run in runs]
    run_form.lane.data = next(i for i in range(1, len(lanes) + 2) if i not in lanes)

    return render_template("experiment_page.html", run_form=run_form, experiment=experiment, runs=runs)