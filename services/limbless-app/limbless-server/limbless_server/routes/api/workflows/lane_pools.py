from typing import TYPE_CHECKING

from flask import Blueprint, request, abort
from flask_login import login_required

from limbless_db import models, DBSession
from limbless_db.categories import HTTPResponse
from .... import db
from ....forms import workflows as wf

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

lane_pools_workflow = Blueprint("lane_pools_workflow", __name__, url_prefix="/api/workflows/lane_pools/")


@lane_pools_workflow.route("available_experiments", methods=["GET"])
@login_required
def available_experiments(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
        
    return wf.lane_pools.SelectExperimentForm().make_response()


@lane_pools_workflow.route("<int:experiment_id>/check_barcodes", methods=["POST"])
@login_required
def check_barcodes(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)

    return wf.lane_pools.BarcodeCheckForm(experiment, request.form).process_request()


@lane_pools_workflow.route("<int:experiment_id>/calculate_ratios", methods=["POST"])
@login_required
def calculate_ratios(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)

    return wf.lane_pools.PoolingRatioForm(experiment, request.form).process_request()