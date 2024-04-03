from typing import TYPE_CHECKING

from flask import Blueprint, request, abort
from flask_login import login_required

from limbless_db import models, DBSession
from limbless_db.categories import HTTPResponse

from .... import db, logger
from ....forms.workflows import lane_qc as wff

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

lane_qc_workflow = Blueprint("lane_qc_workflow", __name__, url_prefix="/api/workflows/lane_qc/")


@lane_qc_workflow.route("<int:experiment_id>/begin", methods=["GET"])
@login_required
def begin(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)

    form = wff.QCLanesForm()
    context = form.prepare(experiment)
    return form.make_response(experiment=experiment, **context)


@lane_qc_workflow.route("<int:experiment_id>/qc", methods=["POST"])
@login_required
def qc(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)

        return wff.QCLanesForm(formdata=request.form).process_request(experiment=experiment, session=session)
