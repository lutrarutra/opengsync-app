from typing import TYPE_CHECKING

from flask import Blueprint, request, abort
from flask_login import login_required

from opengsync_db import models, db_session
from opengsync_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms.workflows import dilute_pools as wff

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

dilute_pools_workflow = Blueprint("dilute_pools_workflow", __name__, url_prefix="/api/workflows/dilute_pools/")


@dilute_pools_workflow.route("<int:experiment_id>/begin", methods=["GET"])
@db_session(db)
@login_required
def begin(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    form = wff.DilutePoolsForm()
    context = form.prepare(experiment)
    return form.make_response(experiment=experiment, **context)


@dilute_pools_workflow.route("<int:experiment_id>/dilute", methods=["POST"])
@db_session(db)
@login_required
def dilute(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return wff.DilutePoolsForm(formdata=request.form).process_request(experiment=experiment, user=current_user)
