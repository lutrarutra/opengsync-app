from typing import TYPE_CHECKING

from flask import Blueprint, request, abort

from opengsync_db import models
from opengsync_db.categories import HTTPResponse

from .... import db, logger, htmx_route  # noqa
from ....forms.workflows import dilute_pools as wff

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

dilute_pools_workflow = Blueprint("dilute_pools_workflow", __name__, url_prefix="/api/workflows/dilute_pools/")


@htmx_route(dilute_pools_workflow, db=db)
def begin(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    form = wff.DilutePoolsForm()
    context = form.prepare(experiment)
    return form.make_response(experiment=experiment, **context)


@htmx_route(dilute_pools_workflow, db=db, methods=["POST"])
def dilute(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return wff.DilutePoolsForm(formdata=request.form).process_request(experiment=experiment, user=current_user)
