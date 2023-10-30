from flask import Blueprint, url_for, render_template, flash, abort, request
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, forms, logger, models
from ....categories import UserRole, HttpResponse
from ....core.DBSession import DBSession

experiments_htmx = Blueprint("experiments_htmx", __name__, url_prefix="/api/experiments/")


@experiments_htmx.route("get/<int:page>")
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    reversed = order == "desc"

    if sort_by not in models.Experiment.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    with DBSession(db.db_handler) as session:
        n_pages = int(session.get_num_experiments() / 20)
        page = min(page, n_pages)
        experiments = session.get_experiments(
            limit=20, offset=20 * page, sort_by=sort_by, reversed=reversed
        )

    return make_response(
        render_template(
            "components/tables/experiment.html",
            experiments=experiments,
            n_pages=n_pages, active_page=page,
            current_sort=sort_by, current_sort_order=order
        ), push_url=False
    )


@experiments_htmx.route("create", methods=["POST"])
@login_required
def create():
    if current_user.role_type not in UserRole.insiders:
        return abort(HttpResponse.FORBIDDEN.value.id)

    experiment_form = forms.ExperimentForm()

    validated, experiment_form = experiment_form.custom_validate(
        db_handler=db.db_handler,
        user_id=current_user.id,
    )

    if not validated:
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
        r1_cycles=experiment_form.r1_cycles.data,
        r2_cycles=experiment_form.r2_cycles.data,
        i1_cycles=experiment_form.i1_cycles.data,
        i2_cycles=experiment_form.i2_cycles.data,
    )

    logger.debug(f"Created experiment on flowcell '{experiment.flowcell}'")
    flash(f"Created experiment on flowcell '{experiment.flowcell}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
    )


@experiments_htmx.route("delete/<int:experiment_id>", methods=["GET"])
@login_required
def delete(experiment_id: int):
    if current_user.role_type not in UserRole.insiders:
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
    
