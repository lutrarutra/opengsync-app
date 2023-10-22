from flask import Blueprint, redirect, url_for, render_template, flash, abort
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, logger, forms
from ....categories import HttpResponse, UserRole

runs_htmx = Blueprint("runs_htmx", __name__, url_prefix="/api/runs/")


@runs_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page):
    n_pages = int(db.db_handler.get_num_runs() / 20)
    page = min(page, n_pages)

    runs = db.db_handler.get_runs(limit=20, offset=20 * page)
    return make_response(
        render_template(
            "components/tables/run.html", runs=runs,
            n_pages=n_pages, active_page=page
        ), push_url=False
    )


@runs_htmx.route("create/<int:experiment_id>", methods=["POST"])
@login_required
def create(experiment_id: int):
    run_form = forms.RunForm()

    if current_user.role_type not in [UserRole.ADMIN, UserRole.BIOINFORMATICIAN, UserRole.TECHNICIAN]:
        return abort(HttpResponse.FORBIDDEN.value.id)

    if not run_form.validate_on_submit():
        template = render_template(
            "forms/run.html", run_form=run_form
        )
        return make_response(
            template, push_url=False
        )

    experiment_runs = db.db_handler.get_experiment_runs(experiment_id)
    if run_form.lane.data in [run.lane for run in experiment_runs]:
        run_form.lane.errors.append("Lane already exists in experiment.")
        template = render_template(
            "forms/run.html", run_form=run_form
        )
        return make_response(
            template, push_url=False
        )

    run = db.db_handler.create_run(
        lane=run_form.lane.data,
        experiment_id=experiment_id,
        r1_cycles=run_form.r1_cycles.data,
        r2_cycles=run_form.r2_cycles.data,
        i1_cycles=run_form.i1_cycles.data,
        i2_cycles=run_form.i2_cycles.data,
    )

    logger.debug("Created run.")
    flash(f"Added new run for lane '{run.lane}'", "success")

    return make_response(
        redirect=url_for("runs_page.run_page", run_id=run.id),
    )


@runs_htmx.route("<int:run_id>/edit", methods=["POST"])
@login_required
def edit(run_id):
    run = db.db_handler.get_run(run_id)
    if not run:
        return redirect("/runs")

    run_form = forms.RunForm()

    if not run_form.validate_on_submit():
        template = render_template(
            "forms/run.html", run_form=run_form, run_id=run_id
        )
        return make_response(
            template, push_url=False
        )

    if run_form.lane.data != run.lane:
        experiment_runs = db.db_handler.get_experiment_runs(run.experiment_id)
        if run_form.lane.data in [run.lane for run in experiment_runs]:
            run_form.lane.errors.append("Lane already exists in experiment.")
            template = render_template(
                "forms/run.html", run_form=run_form, run_id=run_id
            )
            return make_response(
                template, push_url=False
            )

    db.db_handler.update_run(
        run_id, lane=run_form.lane.data,
        r1_cycles=run_form.r1_cycles.data,
        r2_cycles=run_form.r2_cycles.data,
        i1_cycles=run_form.i1_cycles.data,
        i2_cycles=run_form.i2_cycles.data,
    )

    logger.debug(f"Edited {run}")
    flash("Changes saved succesfully!", "success")

    return make_response(
        redirect=url_for("runs_page.run_page", run_id=run_id),
    )
