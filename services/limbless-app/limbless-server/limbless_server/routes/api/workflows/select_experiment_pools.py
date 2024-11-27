from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, flash, url_for
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession
from limbless_db.categories import HTTPResponse, PoolStatus

from limbless_db import db_session

from .... import db, logger  # noqa
from ....forms import SelectSamplesForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

select_experiment_pools_workflow = Blueprint("select_experiment_pools_workflow", __name__, url_prefix="/api/workflows/select_experiment_pools/")


@select_experiment_pools_workflow.route("<int:experiment_id>/begin", methods=["GET"])
@login_required
def begin(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    with DBSession(db) as session:
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        experiment.pools
    
    context = {"experiment": experiment}
    form = SelectSamplesForm(
        workflow="select_experiment_pools", context=context,
        pool_status_filter=[PoolStatus.STORED],
        select_lanes=False,
        select_libraries=False,
        select_samples=False,
    )
    return form.make_response()


@select_experiment_pools_workflow.route("select", methods=["POST"])
@db_session(db)
@login_required
def select():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    context = {}
    if (experiment_id := request.form.get("experiment_id")) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    try:
        experiment_id = int(experiment_id)
        if (experiment := db.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        experiment.pools
        
        context["experiment"] = experiment
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)

    form: SelectSamplesForm = SelectSamplesForm(workflow="ba_report", formdata=request.form, context=context)
    if not form.validate():
        return form.make_response()

    current_pool_ids = [pool.id for pool in experiment.pools]

    for _, row in form.pool_table.iterrows():
        try:
            pool_id = int(row["id"])
        except ValueError:
            logger.error(f"{row['id']} is not a valid pool id")
            raise ValueError("Invalid pool id")
        
        if (_ := db.get_pool(pool_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if pool_id not in current_pool_ids:
            db.link_pool_experiment(experiment_id=experiment.id, pool_id=pool_id)

    flash("Pools linked to experiment", "success")
    return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))