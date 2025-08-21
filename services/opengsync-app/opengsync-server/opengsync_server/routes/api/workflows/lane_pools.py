from flask import Blueprint, request, abort

from opengsync_db import models
from opengsync_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms.workflows import lane_pools as wff
from ....core import wrappers

lane_pools_workflow = Blueprint("lane_pools_workflow", __name__, url_prefix="/api/workflows/lane_pools/")


@wrappers.htmx_route(lane_pools_workflow, db=db)
def begin(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if experiment.workflow.combined_lanes:
        form = wff.UnifiedLanePoolingForm(experiment=experiment)
    else:
        form = wff.LanePoolingForm(experiment=experiment)
    return form.make_response()


@wrappers.htmx_route(lane_pools_workflow, db=db, methods=["POST"])
def lane_pools(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if experiment.workflow.combined_lanes:
        form = wff.UnifiedLanePoolingForm(experiment=experiment, formdata=request.form)
    else:
        form = wff.LanePoolingForm(experiment=experiment, formdata=request.form)

    return form.process_request(user=current_user)