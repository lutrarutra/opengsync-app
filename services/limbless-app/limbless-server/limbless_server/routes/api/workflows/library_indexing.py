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


@library_indexing_workflow.route("<int:lab_prep_id>/download_barcode_table_template", methods=["GET"])
@login_required
def download_barcode_table_template(lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.BarcodeInputForm(lab_prep=lab_prep)
    template = form.get_template()

    return Response(
        template.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={lab_prep.name}_indexing.tsv"}
    )


@library_indexing_workflow.route("<int:lab_prep_id>/begin", methods=["GET"])
@db_session(db)
@login_required
def begin(lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.BarcodeInputForm(lab_prep=lab_prep, formdata=request.form)
    form.prepare()
    return form.make_response()
    

@library_indexing_workflow.route("<int:lab_prep_id>/parse_barcodes", methods=["POST"])
@db_session(db)
@login_required
def parse_barcodes(lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if (input_type := request.args.get("input_type")) not in ["spreadsheet", "plate"]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    form = forms.BarcodeInputForm(lab_prep=lab_prep, input_type=input_type, formdata=request.form)
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