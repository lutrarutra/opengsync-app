from flask import Blueprint, request, abort, Response

from opengsync_db import models
from opengsync_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms.workflows import dist_reads as forms
from ....core import wrappers

dist_reads_workflow = Blueprint("dist_reads_workflow", __name__, url_prefix="/api/workflows/dist_reads/")


@wrappers.htmx_route(dist_reads_workflow, db=db)
def begin(current_user: models.User, experiment_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if experiment.workflow.combined_lanes:
        form = forms.DistributeReadsCombinedForm(experiment=experiment)
    else:
        form = forms.DistributeReadsSeparateForm(experiment=experiment)
    
    return form.make_response()


@wrappers.htmx_route(dist_reads_workflow, db=db, methods=["POST"])
def submit(current_user: models.User, experiment_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if experiment.workflow.combined_lanes:
        form = forms.DistributeReadsCombinedForm(experiment=experiment, formdata=request.form)
    else:
        form = forms.DistributeReadsSeparateForm(experiment=experiment, formdata=request.form)
    
    return form.process_request()