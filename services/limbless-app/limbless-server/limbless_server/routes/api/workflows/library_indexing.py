from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response
from flask_login import login_required

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms.workflows import library_indexing as forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

library_indexing_workflow = Blueprint("library_indexing_workflow", __name__, url_prefix="/api/workflows/library_indexing/")


@library_indexing_workflow.route("<int:lab_prep_id>/begin", methods=["GET"])
@db_session(db)
@login_required
def begin(lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.BarcodeInputForm(lab_prep=lab_prep)
    return form.make_response()
    

@library_indexing_workflow.route("<int:lab_prep_id>/parse_barcodes", methods=["POST"])
@db_session(db)
@login_required
def parse_barcodes(lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.BarcodeInputForm(lab_prep=lab_prep, formdata=request.form)
    return form.process_request()


@library_indexing_workflow.route("map_index_kits", methods=["POST"])
@db_session(db)
@login_required
def map_index_kits() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.IndexKitMappingForm(formdata=request.form)
    return form.process_request()


@library_indexing_workflow.route("complete_pooling", methods=["POST"])
@db_session(db)
@login_required
def complete_pooling() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.CompleteLibraryIndexingForm(formdata=request.form)
    return form.process_request(user=current_user)