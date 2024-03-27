from typing import TYPE_CHECKING

from flask import Blueprint, request, abort
from flask_login import login_required

from limbless_db import models, DBSession
from limbless_db.categories import HTTPResponse

from .... import db, logger
from ....forms.workflows import lane_pools as wff

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

lane_pools_workflow = Blueprint("lane_pools_workflow", __name__, url_prefix="/api/workflows/lane_pools/")


@lane_pools_workflow.route("<int:experiment_id>/begin", methods=["GET"])
@login_required
def begin(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)

    form = wff.LanePoolingForm()
    context = form.prepare(experiment_id)
    return form.make_response(experiment=experiment, Pool=models.Pool, **context)


@lane_pools_workflow.route("<int:experiment_id>/lane_pools", methods=["POST"])
@login_required
def lane_pools(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        experiment.files

    return wff.LanePoolingForm(formdata=request.form).process_request(experiment=experiment, user=current_user)