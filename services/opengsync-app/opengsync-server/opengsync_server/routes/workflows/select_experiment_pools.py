from flask import Blueprint, request, flash, url_for
from flask_htmx import make_response

from opengsync_db import models

from ... import db, logger
from ...core import wrappers, exceptions
from ...forms import SelectSamplesForm

select_experiment_pools_workflow = Blueprint("select_experiment_pools_workflow", __name__, url_prefix="/workflows/select_experiment_pools/")


@wrappers.htmx_route(select_experiment_pools_workflow, db=db)
def begin(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    context = {"experiment": experiment}
    form = SelectSamplesForm.create_workflow_form(workflow="select_experiment_pools", context=context)
    return form.make_response()


@wrappers.htmx_route(select_experiment_pools_workflow, db=db, methods=["POST"])
def select(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    context = {}
    if (experiment_id := request.form.get("experiment_id")) is None:
        raise exceptions.BadRequestException()
    try:
        experiment_id = int(experiment_id)
        if (experiment := db.experiments.get(experiment_id)) is None:
            raise exceptions.NotFoundException()
        
        experiment.pools
        
        context["experiment"] = experiment
    except ValueError:
        raise exceptions.BadRequestException()

    form: SelectSamplesForm = SelectSamplesForm.create_workflow_form(workflow="select_experiment_pools", formdata=request.form, context=context)
    if not form.validate():
        return form.make_response()

    current_pool_ids = [pool.id for pool in experiment.pools]

    for _, row in form.pool_table.iterrows():
        try:
            pool_id = int(row["id"])
        except ValueError:
            logger.error(f"{row['id']} is not a valid pool id")
            raise ValueError("Invalid pool id")
        
        if (_ := db.pools.get(pool_id)) is None:
            raise exceptions.NotFoundException()
        
        if pool_id not in current_pool_ids:
            db.links.link_pool_experiment(experiment_id=experiment.id, pool_id=pool_id)

    flash("Pools linked to experiment", "success")
    return make_response(redirect=url_for("experiments_page.experiment", experiment_id=experiment.id))