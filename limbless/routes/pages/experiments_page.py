from flask import Blueprint, render_template, redirect, url_for, abort
from flask_login import login_required, current_user

from ...core import DBSession
from ... import forms, db, logger, PAGE_LIMIT
from ...categories import UserRole, HttpResponse

experiments_page_bp = Blueprint("experiments_page", __name__)


@experiments_page_bp.route("/experiments")
@login_required
def experiments_page():
    if not current_user.is_insider():
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    experiments, n_pages = db.db_handler.get_experiments()

    experiment_form = forms.ExperimentForm()
    experiment_form.sequencing_person.data = current_user.id

    return render_template(
        "experiments_page.html", experiment_form=experiment_form,
        experiments=experiments,
        n_pages=n_pages, active_page=0,
        current_sort="id", current_sort_order="desc"
    )


@experiments_page_bp.route("/experiments/<experiment_id>")
@login_required
def experiment_page(experiment_id):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    with DBSession(db.db_handler) as session:
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        access = session.get_user_experiment_access(current_user.id, experiment_id)
        if access is None:
            return abort(HttpResponse.FORBIDDEN.value.id)

        libraries = experiment.libraries
        available_libraries, n_pages = session.get_libraries(limit=PAGE_LIMIT)
        experiment_lanes = session.get_lanes_in_experiment(experiment_id)

        experiment_form = forms.ExperimentForm()
        experiment_form.flowcell.data = experiment.flowcell
        experiment_form.sequencer.data = experiment.sequencer.id
        experiment_form.r1_cycles.data = experiment.r1_cycles
        experiment_form.r2_cycles.data = experiment.r2_cycles
        experiment_form.i1_cycles.data = experiment.i1_cycles
        experiment_form.i2_cycles.data = experiment.i2_cycles
        experiment_form.num_lanes.data = experiment.num_lanes
        experiment_form.sequencing_person.data = experiment.sequencing_person_id

    path_list = [
        ("Experiments", url_for("experiments_page.experiments_page")),
        (f"{experiment_id}", ""),
    ]

    return render_template(
        "experiment_page.html",
        experiment=experiment,
        experiment_form=experiment_form,
        experiment_lanes=experiment_lanes,
        libraries=libraries,
        path_list=path_list,
        available_libraries=available_libraries,
        selected_sequencer=experiment.sequencer.name,
        selected_user=experiment.sequencing_person,
        n_pages=n_pages, active_page=0,
    )
