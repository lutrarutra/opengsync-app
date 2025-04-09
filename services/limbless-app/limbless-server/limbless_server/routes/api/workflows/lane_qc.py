from typing import TYPE_CHECKING

from flask import Blueprint, request, abort
from flask_login import login_required

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse

from .... import db, logger  # noqa F401
from ....forms.workflows import lane_qc as wff

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

lane_qc_workflow = Blueprint("lane_qc_workflow", __name__, url_prefix="/api/workflows/lane_qc/")


@lane_qc_workflow.route("<int:experiment_id>/begin", methods=["GET"])
@db_session(db)
@login_required
def begin(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if experiment.workflow.combined_lanes:
        form = wff.UnifiedQCLanesForm(experiment=experiment)
    else:
        form = wff.QCLanesForm(experiment=experiment)
    return form.make_response()


@lane_qc_workflow.route("<int:experiment_id>/qc", methods=["POST"])
@db_session(db)
@login_required
def qc(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if experiment.workflow.combined_lanes:
        form = wff.UnifiedQCLanesForm(experiment=experiment, formdata=request.form)
    else:
        form = wff.QCLanesForm(experiment=experiment, formdata=request.form)
        
    return form.process_request()
