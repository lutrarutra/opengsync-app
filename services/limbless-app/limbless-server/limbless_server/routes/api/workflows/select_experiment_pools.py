from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, render_template, flash, url_for
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession
from limbless_db.categories import HTTPResponse, PoolStatus, ExperimentStatus

from .... import db, logger

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

select_experiment_pools_workflow = Blueprint("select_experiment_pools_workflow", __name__, url_prefix="/api/workflows/select_experiment_pools/")


@select_experiment_pools_workflow.route("<int:experiment_id>/begin", methods=["GET"])
@login_required
def begin(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        available_pools, n_available_pools_pages = session.get_pools(sort_by="id", descending=True, status=PoolStatus.ACCEPTED)
        selected_pools, _ = session.get_pools(sort_by="id", descending=True, experiment_id=experiment_id, limit=None)

        return make_response(
            render_template(
                "workflows/select_experiment_pools/sp-1.html",
                experiment=experiment, available_pools=available_pools, n_available_pools_pages=n_available_pools_pages,
                available_pools_active_page=0, selected_pools=selected_pools, active_tab=0
            )
        )
    

@select_experiment_pools_workflow.route("<int:experiment_id>/add_pool", methods=["POST"])
@login_required
def add_pool(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (pool_id := request.form.get("pool_id")) is None:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        try:
            pool_id = int(pool_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if (_ := session.get_pool(pool_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)

        session.link_pool_experiment(experiment_id=experiment_id, pool_id=pool_id)

        available_pools, n_available_pools_pages = session.get_pools(sort_by="id", descending=True, status=PoolStatus.ACCEPTED)
        selected_pools, _ = session.get_pools(sort_by="id", descending=True, experiment_id=experiment_id, limit=None)

        qc_done = len(experiment.pools) > 0
        for pool in experiment.pools:
            qc_done = qc_done and pool.is_qced()
            if qc_done is False:
                break
            
        if qc_done:
            experiment.status_id = ExperimentStatus.POOLS_QCED.id
            experiment = session.update_experiment(experiment)
        experiment = session.update_experiment(experiment)

        return make_response(
            render_template(
                "workflows/select_experiment_pools/container.html",
                experiment=experiment, available_pools=available_pools, n_available_pools_pages=n_available_pools_pages,
                available_pools_active_page=0, selected_pools=selected_pools,
                active_tab=0
            )
        )
    

@select_experiment_pools_workflow.route("<int:experiment_id>/remove_pool", methods=["DELETE"])
@login_required
def remove_pool(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if (pool_id := request.args.get("pool_id")) is None:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        try:
            pool_id = int(pool_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if (_ := session.get_pool(pool_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)

        session.unlink_pool_experiment(experiment_id=experiment_id, pool_id=pool_id)

        available_pools, n_available_pools_pages = session.get_pools(sort_by="id", descending=True, status=PoolStatus.ACCEPTED)
        selected_pools, _ = session.get_pools(sort_by="id", descending=True, experiment_id=experiment_id, limit=None)

        qc_done = len(experiment.pools) > 0
        for pool in experiment.pools:
            qc_done = qc_done and pool.is_qced()
            if qc_done is False:
                break
            
        if qc_done:
            experiment.status_id = ExperimentStatus.POOLS_QCED.id
            experiment = session.update_experiment(experiment)

        return make_response(
            render_template(
                "workflows/select_experiment_pools/container.html",
                experiment=experiment, available_pools=available_pools, n_available_pools_pages=n_available_pools_pages,
                available_pools_active_page=0, selected_pools=selected_pools, active_tab=1
            )
        )