from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response, render_template, flash, url_for
from flask_login import login_required
from flask_htmx import make_response

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse, LibraryStatus, LibraryType

from .... import db, logger  # noqa
from ....forms.workflows import pool_indexing as forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

pool_indexing_workflow = Blueprint("pool_indexing_workflow", __name__, url_prefix="/api/workflows/pool_indexing/")


@pool_indexing_workflow.route("<int:pool_id>/download_barcode_table_template", methods=["GET"])
@login_required
def download_barcode_table_template(pool_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.BarcodeInputForm(pool=pool)
    template = form.get_template()

    return Response(
        template.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=pooling_{pool.name}.tsv"}
    )


@pool_indexing_workflow.route("<int:pool_id>/begin", methods=["GET"])
@db_session(db)
@login_required
def begin(pool_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.BarcodeInputForm(pool=pool, formdata=request.form)
    form.prepare()
    return form.make_response()
    

@pool_indexing_workflow.route("<int:pool_id>/parse_barcodes", methods=["POST"])
@db_session(db)
@login_required
def parse_barcodes(pool_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if (input_type := request.args.get("input_type")) not in ["file", "spreadsheet", "plate"]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    form = forms.BarcodeInputForm(pool=pool, input_type=input_type, formdata=request.form | request.files)
    return form.process_request()


@pool_indexing_workflow.route("map_index_kits", methods=["POST"])
@login_required
def map_index_kits() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.IndexKitMappingForm(formdata=request.form)
    return form.process_request()


@pool_indexing_workflow.route("complete_pooling", methods=["POST"])
@login_required
def complete_pooling() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.CompleteLibraryIndexingForm(formdata=request.form)
    return form.process_request(user=current_user)