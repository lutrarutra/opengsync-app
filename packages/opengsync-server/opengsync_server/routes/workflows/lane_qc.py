from flask import Blueprint, request

from opengsync_db import models

from ... import db, logger
from ...forms.workflows import lane_qc as wff
from ...core import wrappers, exceptions

lane_qc_workflow = Blueprint("lane_qc_workflow", __name__, url_prefix="/workflows/lane_qc/")


@wrappers.htmx_route(lane_qc_workflow, db=db)
def begin(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()

    if experiment.workflow.combined_lanes:
        form = wff.UnifiedQCLanesForm(experiment=experiment)
    else:
        form = wff.QCLanesForm(experiment=experiment)
    return form.make_response()


@wrappers.htmx_route(lane_qc_workflow, db=db, methods=["POST"])
def qc(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()

    if experiment.workflow.combined_lanes:
        form = wff.UnifiedQCLanesForm(experiment=experiment, formdata=request.form)
    else:
        form = wff.QCLanesForm(experiment=experiment, formdata=request.form)
        
    return form.process_request()
