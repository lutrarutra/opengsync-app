from flask import Blueprint, request, Response

from opengsync_db import models

from ... import db, logger
from ...forms.workflows import dist_reads as forms
from ...core import wrappers, exceptions

dist_reads_workflow = Blueprint("dist_reads_workflow", __name__, url_prefix="/workflows/dist_reads/")


@wrappers.htmx_route(dist_reads_workflow, db=db)
def begin(current_user: models.User, experiment_id: int) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if experiment.workflow.combined_lanes:
        form = forms.DistributeReadsCombinedForm(experiment=experiment, current_user=current_user)
    else:
        form = forms.DistributeReadsSeparateForm(experiment=experiment, current_user=current_user)
    
    return form.make_response()


@wrappers.htmx_route(dist_reads_workflow, db=db, methods=["POST"])
def submit(current_user: models.User, experiment_id: int) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if experiment.workflow.combined_lanes:
        form = forms.DistributeReadsCombinedForm(experiment=experiment, current_user=current_user, formdata=request.form)
    else:
        form = forms.DistributeReadsSeparateForm(experiment=experiment, current_user=current_user, formdata=request.form)
    
    return form.process_request()