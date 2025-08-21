from flask import Blueprint, request, abort

from opengsync_db import models
from opengsync_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms.workflows import dilute_pools as wff
from ....core import wrappers

dilute_pools_workflow = Blueprint("dilute_pools_workflow", __name__, url_prefix="/api/workflows/dilute_pools/")


@wrappers.htmx_route(dilute_pools_workflow, db=db)
def begin(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    form = wff.DilutePoolsForm(experiment=experiment)
    return form.make_response()


@wrappers.htmx_route(dilute_pools_workflow, db=db, methods=["POST"])
def dilute(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return wff.DilutePoolsForm(experiment=experiment, formdata=request.form).process_request(user=current_user)
