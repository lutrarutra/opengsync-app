from flask import Blueprint, render_template, redirect, url_for, abort
from flask_login import login_required, current_user

from ...core import DBSession
from ... import forms, db
from ...categories import UserRole, HttpResponse

experiments_page_bp = Blueprint("experiments_page", __name__)


@experiments_page_bp.route("/experiments")
@login_required
def experiments_page():
    if current_user.role_type == UserRole.CLIENT:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    experiment_form = forms.ExperimentForm()
    with DBSession(db.db_handler) as session:
        experiments = session.get_experiments()
        n_pages = int(session.get_num_experiments() / 20)

    return render_template(
        "experiments_page.html", experiment_form=experiment_form,
        experiments=experiments,
        n_pages=n_pages, active_page=0,
        current_sort="id", current_sort_order="asc"
    )


@experiments_page_bp.route("/experiments/<experiment_id>")
@login_required
def experiment_page(experiment_id):
    with DBSession(db.db_handler) as session:
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        access = session.get_user_experiment_access(current_user.id, experiment_id)
        if access is None:
            return abort(HttpResponse.FORBIDDEN.value.id)

    with DBSession(db.db_handler) as session:
        experiment = db.db_handler.get_experiment(experiment_id)
        if not experiment:
            return redirect(url_for("experiments_page.experiments_page"))
        
        experiment_form = forms.ExperimentForm()
        experiment_form.flowcell.data = experiment.flowcell
        experiment_form.sequencer.data = experiment.sequencer.id

        run_form = forms.RunForm()
        lanes = [run.lane for run in experiment.runs]
        run_form.lane.data = next(i for i in range(1, len(lanes) + 2) if i not in lanes)

    return render_template(
        "experiment_page.html", run_form=run_form, experiment=experiment,
        experiment_form=experiment_form,
        selected_sequencer=experiment.sequencer.name,
    )
