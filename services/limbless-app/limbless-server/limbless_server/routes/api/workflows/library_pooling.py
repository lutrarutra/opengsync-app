from typing import TYPE_CHECKING, Literal

from flask import Blueprint, request, abort, Response, render_template
from flask_login import login_required
from flask_htmx import make_response

from limbless_db import models, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, LibraryStatus

from .... import db, logger
from ....forms.workflows import library_pooling as forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

library_pooling_workflow = Blueprint("library_pooling_workflow", __name__, url_prefix="/api/workflows/library_pooling/")


@library_pooling_workflow.route("get_libraries/<int:page>", methods=["GET"])
@login_required
def get_libraries(page: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page
    
    libraries, n_pages = db.get_libraries(status=LibraryStatus.ACCEPTED, sort_by=sort_by, descending=descending, offset=offset)
    return make_response(
        render_template(
            "workflows/library_pooling/select-libraries-table.html",
            libraries=libraries, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order
        )
    )


@library_pooling_workflow.route("table_query/<string:field_name>", methods=["POST"])
@login_required
def table_query(field_name: str) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (word := request.form.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if field_name == "name":
        libraries = db.query_libraries(word, status=LibraryStatus.ACCEPTED)
    elif field_name == "id":
        try:
            _id = int(word)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        libraries = [db.get_library(library_id=_id)]
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    return make_response(
        render_template(
            "components/tables/select-libraries.html",
            libraries=libraries, n_pages=1, active_page=0,
        )
    )


@library_pooling_workflow.route("download_barcode_table_template/<string:uuid>", methods=["GET"])
@login_required
def download_barcode_table_template(uuid: str) -> Response:
    form = forms.BarcodeInputForm(uuid=uuid)
    template = form.get_template()

    return Response(
        template.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=visium_annotation.tsv"}
    )


@library_pooling_workflow.route("begin", methods=["GET"])
@login_required
def begin() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.DefinePoolForm()
    form.prepare(current_user)
    return form.make_response()


@library_pooling_workflow.route("define_pool", methods=["POST"])
@login_required
def define_pool() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.DefinePoolForm(request.form)
    return form.process_request()


@library_pooling_workflow.route("select_libraries", methods=["POST"])
@login_required
def select_libraries() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.SelectLibrariesForm(request.form)
    return form.process_request()


@library_pooling_workflow.route("parse_barcodes/<string:input_type>", methods=["POST"])
@login_required
def parse_barcodes(input_type: Literal["file", "spreadsheet"]) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if input_type not in ["file", "spreadsheet"]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    form = forms.BarcodeInputForm(input_type=input_type, formdata=request.form | request.files)
    return form.process_request()


@library_pooling_workflow.route("map_index_kits", methods=["POST"])
@login_required
def map_index_kits() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.IndexKitMappingForm(formdata=request.form)
    return form.process_request()


@library_pooling_workflow.route("complete_pooling", methods=["POST"])
@login_required
def complete_pooling() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.CompleteLibraryPoolingForm(formdata=request.form)
    return form.process_request(current_user=current_user)