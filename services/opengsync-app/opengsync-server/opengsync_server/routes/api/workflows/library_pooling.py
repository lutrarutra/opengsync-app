from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response
from flask_login import login_required

from opengsync_db import models, db_session
from opengsync_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms.workflows import library_pooling as forms
from ....forms.MultiStepForm import MultiStepForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

library_pooling_workflow = Blueprint("library_pooling_workflow", __name__, url_prefix="/api/workflows/library_pooling/")


@library_pooling_workflow.route("<int:lab_prep_id>/begin", methods=["GET"])
@db_session(db)
@login_required
def begin(lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.BarcodeInputForm(lab_prep=lab_prep, uuid=None, formdata=None)
    return form.make_response()


@library_pooling_workflow.route("<int:lab_prep_id>/previous/<string:uuid>", methods=["GET"])
@db_session(db)
@login_required
def previous(lab_prep_id: int, uuid: str):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if (response := MultiStepForm.pop_last_step("library_pooling", uuid)) is None:
        logger.error("Failed to pop last step")
        return abort(HTTPResponse.INTERNAL_SERVER_ERROR.id)
    
    step_name, step = response

    prev_step_cls = forms.steps[step_name]
    prev_step = prev_step_cls(uuid=uuid, lab_prep=lab_prep, **step.args)  # type: ignore
    prev_step.fill_previous_form(step)
    return prev_step.make_response()


@library_pooling_workflow.route("<int:lab_prep_id>/upload_barcode_form/<string:uuid>", methods=["POST"])
@db_session(db)
@login_required
def upload_barcode_form(lab_prep_id: int, uuid: str) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.BarcodeInputForm(uuid=uuid, lab_prep=lab_prep, formdata=request.form)
    return form.process_request()


@library_pooling_workflow.route("<int:lab_prep_id>/map_index_kits/<string:uuid>", methods=["POST"])
@db_session(db)
@login_required
def map_index_kits(lab_prep_id: int, uuid: str) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.IndexKitMappingForm(lab_prep=lab_prep, uuid=uuid, formdata=request.form)
    return form.process_request()


@library_pooling_workflow.route("<int:lab_prep_id>/complete_pooling/<string:uuid>", methods=["POST"])
@db_session(db)
@login_required
def complete_pooling(lab_prep_id: int, uuid: str) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.CompleteLibraryPoolingForm(lab_prep=lab_prep, uuid=uuid, formdata=request.form)
    return form.process_request(user=current_user)