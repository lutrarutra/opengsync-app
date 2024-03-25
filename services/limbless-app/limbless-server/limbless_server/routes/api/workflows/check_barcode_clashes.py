from typing import TYPE_CHECKING

from flask import Blueprint, request, abort
from flask_login import login_required

from limbless_db import models, DBSession
from limbless_db.categories import HTTPResponse

from .... import db
from ....forms.workflows import check_barcode_clashes as wff

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

check_barcode_clashes_workflow = Blueprint("check_barcode_clashes_workflow", __name__, url_prefix="/api/workflows/check_barcode_clashes/")


@check_barcode_clashes_workflow.route("<int:experiment_id>/begin", methods=["GET"])
@login_required
def begin(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)

    form = wff.CheckBarcodeClashesForm()
    context = form.prepare(experiment_id)
    return form.make_response(experiment=experiment, **context)


@check_barcode_clashes_workflow.route("<int:experiment_id>/check_barcodes", methods=["POST"])
@login_required
def check_barcodes(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)

    return wff.CheckBarcodeClashesForm(request.form).process_request(experiment=experiment)
