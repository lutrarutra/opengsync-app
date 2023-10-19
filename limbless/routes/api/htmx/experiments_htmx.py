from flask import Blueprint, url_for, render_template, flash, abort
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, forms, logger
from ....categories import UserRole, HttpResponse

experiments_htmx = Blueprint("experiments_htmx", __name__, url_prefix="/api/experiments/")


@experiments_htmx.route("get/<int:page>")
@login_required
def get(page: int):
    n_pages = int(db.db_handler.get_num_experiments() / 20)
    page = min(page, n_pages)
    experiments = db.db_handler.get_experiments(limit=20, offset=20 * page)

    return make_response(
        render_template(
            "components/tables/experiment.html",
            experiments=experiments,
            n_pages=n_pages, active_page=page
        ), push_url=False
    )

@experiments_htmx.route("create", methods=["POST"])
@login_required
def create():
    experiment_form = forms.ExperimentForm()

    if not experiment_form.validate_on_submit():
        template = render_template(
            "forms/experiment.html",
            experiment_form=experiment_form
        )
        return make_response(
            template, push_url=False
        )

    experiment = db.db_handler.create_experiment(
        flowcell=experiment_form.flowcell.data,
        sequencer_id=experiment_form.sequencer.data,
    )

    logger.debug(f"Created experiment on flowcell '{experiment.flowcell}'")
    flash(f"Created experiment on flowcell '{experiment.flowcell}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
    )


@experiments_htmx.route("delete/<int:experiment_id>", methods=["GET"])
@login_required
def delete(experiment_id: int):
    if current_user.role_type not in [UserRole.ADMIN, UserRole.BIOINFORMATICIAN, UserRole.TECHNICIAN]:
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not experiment.is_deleteable():
        return abort(HttpResponse.FORBIDDEN.value.id)

    db.db_handler.delete_experiment(experiment_id)

    logger.debug(f"Deleted experiment on flowcell '{experiment.flowcell}'")
    flash(f"Deleted experiment on flowcell '{experiment.flowcell}'.", "success")
    
    return make_response(
        redirect=url_for("experiments_page.experiments_page"),
    )
    
