from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response

from opengsync_db import models
from opengsync_db.categories import HTTPResponse

from .... import db, logger, htmx_route  # noqa
from ....forms.workflows import dist_reads as forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

dist_reads_workflow = Blueprint("dist_reads_workflow", __name__, url_prefix="/api/workflows/dist_reads/")


@htmx_route(dist_reads_workflow, db=db)
def begin(experiment_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if experiment.workflow.combined_lanes:
        form = forms.DistributeReadsCombinedForm(experiment=experiment)
    else:
        form = forms.DistributeReadsSeparateForm(experiment=experiment)
    
    return form.make_response()


@htmx_route(dist_reads_workflow, db=db, methods=["POST"])
def submit(experiment_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if experiment.workflow.combined_lanes:
        form = forms.DistributeReadsCombinedForm(experiment=experiment, formdata=request.form)
    else:
        form = forms.DistributeReadsSeparateForm(experiment=experiment, formdata=request.form)
    
    return form.process_request()