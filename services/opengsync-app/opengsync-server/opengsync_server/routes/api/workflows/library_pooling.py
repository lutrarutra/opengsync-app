from flask import Blueprint, request, abort, Response

from opengsync_db import models
from opengsync_db.categories import HTTPResponse

from .... import db, logger
from ....core import wrappers
from ....forms.workflows import library_pooling as forms
from ....forms.MultiStepForm import MultiStepForm

library_pooling_workflow = Blueprint("library_pooling_workflow", __name__, url_prefix="/api/workflows/library_pooling/")


@wrappers.htmx_route(library_pooling_workflow, db=db)
def begin(current_user: models.User, lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.BarcodeInputForm(lab_prep=lab_prep, uuid=None, formdata=None)
    return form.make_response()


@wrappers.htmx_route(library_pooling_workflow, db=db)
def previous(current_user: models.User, lab_prep_id: int, uuid: str):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if (response := MultiStepForm.pop_last_step("library_pooling", uuid)) is None:
        logger.error("Failed to pop last step")
        return abort(HTTPResponse.INTERNAL_SERVER_ERROR.id)
    
    step_name, step = response

    prev_step_cls = forms.steps[step_name]
    prev_step = prev_step_cls(uuid=uuid, lab_prep=lab_prep, formdata=None, **step.args)  # type: ignore
    prev_step.fill_previous_form(step)
    return prev_step.make_response()


@wrappers.htmx_route(library_pooling_workflow, db=db, methods=["POST"])
def upload_barcode_form(current_user: models.User, lab_prep_id: int, uuid: str) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    form = forms.BarcodeInputForm(uuid=uuid, lab_prep=lab_prep, formdata=request.form)
    return form.process_request()


@wrappers.htmx_route(library_pooling_workflow, db=db, methods=["POST"])
def map_index_kits(current_user: models.User, lab_prep_id: int, uuid: str) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.IndexKitMappingForm(lab_prep=lab_prep, uuid=uuid, formdata=request.form)
    return form.process_request()


@wrappers.htmx_route(library_pooling_workflow, db=db, methods=["POST"])
def barcode_match(current_user: models.User, lab_prep_id: int, uuid: str):
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return forms.BarcodeMatchForm(
        uuid=uuid, formdata=request.form,
        lab_prep=lab_prep,
    ).process_request()


@wrappers.htmx_route(library_pooling_workflow, db=db, methods=["POST"])
def complete_pooling(current_user: models.User, lab_prep_id: int, uuid: str) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.CompleteLibraryPoolingForm(lab_prep=lab_prep, uuid=uuid, formdata=request.form)
    return form.process_request(user=current_user)