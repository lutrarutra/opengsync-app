from typing import TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, abort, request
from flask_htmx import make_response
from flask_login import login_required

from .... import db, forms, logger, models, PAGE_LIMIT
from ....categories import HttpResponse, ExperimentStatus
from ....core.DBSession import DBSession

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user

experiments_htmx = Blueprint("experiments_htmx", __name__, url_prefix="/api/experiments/")


@experiments_htmx.route("get/<int:page>")
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Experiment.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    with DBSession(db.db_handler) as session:
        experiments, n_pages = session.get_experiments(
            limit=PAGE_LIMIT, offset=offset, sort_by=sort_by, descending=descending
        )

    return make_response(
        render_template(
            "components/tables/experiment.html",
            experiments=experiments,
            experiments_n_pages=n_pages, experiments_active_page=page,
            experiments_current_sort=sort_by, experiments_current_sort_order=order
        ), push_url=False
    )


@experiments_htmx.route("create", methods=["POST"])
@login_required
def create():
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)

    experiment_form = forms.ExperimentForm()

    validated, experiment_form = experiment_form.custom_validate()

    if (selected_person_id := experiment_form.sequencing_person.data) is not None:
        if (selected_user := db.db_handler.get_user(selected_person_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
    elif experiment_form.current_user_is_seq_person.data:
        selected_user = current_user
    else:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    experiment_form.current_user_is_seq_person.data = current_user.id == selected_user.id

    if not validated:
        return make_response(
            render_template(
                "forms/experiment.html",
                experiment_form=experiment_form,
                selected_user=selected_user
            ), push_url=False
        )

    experiment = db.db_handler.create_experiment(
        flowcell=experiment_form.flowcell.data,
        sequencer_id=experiment_form.sequencer.data,
        r1_cycles=experiment_form.r1_cycles.data,
        r2_cycles=experiment_form.r2_cycles.data,
        i1_cycles=experiment_form.i1_cycles.data,
        i2_cycles=experiment_form.i2_cycles.data,
        num_lanes=experiment_form.num_lanes.data,
        sequencing_person_id=selected_user.id,
    )

    logger.debug(f"Created experiment on flowcell '{experiment.flowcell}'")
    flash(f"Created experiment on flowcell '{experiment.flowcell}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
    )


@experiments_htmx.route("<int:experiment_id>/edit", methods=["POST"])
@login_required
def edit(experiment_id: int):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    experiment_form = forms.ExperimentForm()
    validated, experiment_form = experiment_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "forms/experiment.html",
                experiment_form=experiment_form
            ), push_url=False
        )
    
    db.db_handler.update_experiment(
        experiment_id=experiment_id,
        flowcell=experiment_form.flowcell.data,
        r1_cycles=experiment_form.r1_cycles.data,
        r2_cycles=experiment_form.r2_cycles.data,
        i1_cycles=experiment_form.i1_cycles.data,
        i2_cycles=experiment_form.i2_cycles.data,
        num_lanes=experiment_form.num_lanes.data,
        sequencer_id=experiment_form.sequencer.data,
        sequencing_person_id=experiment_form.sequencing_person.data,
    )

    logger.debug(f"Edited experiment on flowcell '{experiment.flowcell}'")
    flash(f"Edited experiment on flowcell '{experiment.flowcell}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
    )


@experiments_htmx.route("delete/<int:experiment_id>", methods=["POST"])
@login_required
def delete(experiment_id: int):
    if not current_user.is_insider():
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


@experiments_htmx.route("<int:experiment_id>/add_seq_request/<int:seq_request_id>", methods=["POST"])
@login_required
def add_seq_request(experiment_id: int, seq_request_id: int):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not experiment.is_editable():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if not experiment.is_editable():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    link = db.db_handler.link_experiment_seq_request(
        experiment_id=experiment_id,
        seq_request_id=seq_request_id,
    )

    logger.debug(f"Added request '{seq_request.name}' to experiment (id='{experiment_id}')")
    flash(f"Added request '{seq_request.name}' to experiment.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment_id),
        push_url=False
    )

@experiments_htmx.route("<int:experiment_id>/add_pool/<int:pool_id>/<int:lane>", methods=["POST"])
@login_required
def add_pool(experiment_id: int, pool_id: int, lane: int):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if (pool := db.db_handler.get_pool(pool_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if lane > experiment.num_lanes or lane < 1:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if not experiment.is_editable():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    db.db_handler.link_experiment_pool(
        experiment_id=experiment_id,
        pool_id=pool.id,
        lane=lane,
    )

    logger.debug(f"Added pool '{pool.name}' to experiment (id='{experiment_id}') on lane '{lane}'")
    flash(f"Added pool '{pool.name}' to experiment on lane '{lane}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
        push_url=False
    )


@experiments_htmx.route("<int:experiment_id>/remove_pool/<int:pool_id>/<int:lane>", methods=["DELETE"])
@login_required
def remove_pool(experiment_id: int, pool_id: int, lane: int):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if (pool := db.db_handler.get_pool(pool_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if lane > experiment.num_lanes or lane < 1:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if not experiment.is_editable():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    db.db_handler.unlink_experiment_pool(
        experiment_id=experiment_id,
        pool_id=pool_id,
        lane=lane,
    )

    logger.debug(f"Removed pool '{pool.name}' from experiment  (id='{experiment_id}') on lane '{lane}'")
    flash(f"Removed pool '{pool.name}' from experiment on lane '{lane}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
        push_url=False
    )


@experiments_htmx.route("<int:experiment_id>/remove_seq_request", methods=["DELETE"])
@login_required
def remove_seq_request(experiment_id: int):
    if (request_id := request.args.get("request_id", None)) is not None:
        logger.debug(f"Request id: {request_id}")
        try:
            seq_request_id = int(request_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
    else:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not experiment.is_editable():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    db.db_handler.unlink_experiment_seq_request(
        experiment_id=experiment_id,
        seq_request_id=seq_request_id,
    )

    logger.debug(f"Removed request '{seq_request.name}' from experiment (id='{experiment_id}')")
    flash(f"Removed request '{seq_request.name}' from experiment.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
        push_url=False
    )
    

@experiments_htmx.route("select_sequencing_person", methods=["POST"])
@login_required
def select_sequencing_person():
    experiment_form = forms.ExperimentForm()

    if (selected_person_id := experiment_form.sequencing_person.data) is not None:
        if (selected_user := db.db_handler.get_user(selected_person_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
    elif experiment_form.current_user_is_seq_person.data:
        selected_user = current_user
    else:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    experiment_form.current_user_is_seq_person.data = current_user.id == selected_user.id

    return make_response(
        render_template(
            "forms/experiment.html",
            experiment_form=experiment_form,
            selected_user=selected_user
        ), push_url=False
    )


@experiments_htmx.route("<int:experiment_id>/submit_experiment", methods=["POST"])
@login_required
def submit_experiment(experiment_id: int):
    with DBSession(db.db_handler) as session:
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if not experiment.is_submittable():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        session.update_experiment(
            experiment_id=experiment_id,
            status=ExperimentStatus.SEQUENCING
        )

    logger.debug(f"Submitted experiment on flowcell '{experiment.flowcell}'")
    flash(f"Submitted experiment on flowcell '{experiment.flowcell}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
    )
