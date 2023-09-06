from flask import Blueprint, url_for, render_template, flash
from flask_htmx import make_response
from flask_login import login_required

from .... import db, forms, logger

experiments_htmx = Blueprint("experiments_htmx", __name__, url_prefix="/api/experiments/")


@login_required
@experiments_htmx.route("get/<int:page>")
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


@login_required
@experiments_htmx.route("create", methods=["POST"])
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
        name=experiment_form.name.data,
        flowcell=experiment_form.flowcell.data
    )

    logger.debug(f"Created experiment {experiment.name}.")
    flash(f"Created experiment {experiment.name}.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
    )
