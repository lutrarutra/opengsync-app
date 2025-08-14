from flask import Blueprint, request, abort

from opengsync_db import models
from opengsync_db.categories import HTTPResponse

from .... import db, logger  # noqa F401
from ....forms.workflows import lane_qc as wff
from ....core import wrappers

lane_qc_workflow = Blueprint("lane_qc_workflow", __name__, url_prefix="/api/workflows/lane_qc/")


@wrappers.htmx_route(lane_qc_workflow, db=db)
def begin(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if experiment.workflow.combined_lanes:
        form = wff.UnifiedQCLanesForm(experiment=experiment)
    else:
        form = wff.QCLanesForm(experiment=experiment)
    return form.make_response()


@wrappers.htmx_route(lane_qc_workflow, db=db, methods=["POST"])
def qc(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if experiment.workflow.combined_lanes:
        form = wff.UnifiedQCLanesForm(experiment=experiment, formdata=request.form)
    else:
        form = wff.QCLanesForm(experiment=experiment, formdata=request.form)
        
    return form.process_request()
