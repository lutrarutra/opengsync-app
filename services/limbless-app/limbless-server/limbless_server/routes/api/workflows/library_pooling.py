import json
from typing import TYPE_CHECKING, Literal

from flask import Blueprint, request, abort, Response, render_template
from flask_login import login_required
from flask_htmx import make_response

from limbless_db import models, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, LibraryStatus, LibraryType

from .... import db, logger  # noqa
from ....forms.workflows import library_pooling as forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

library_pooling_workflow = Blueprint("library_pooling_workflow", __name__, url_prefix="/api/workflows/library_pooling/")


@library_pooling_workflow.route("get_libraries", methods=["GET"], defaults={"page": 0})
@library_pooling_workflow.route("get_libraries/<int:page>", methods=["GET"])
@login_required
def get_libraries(page: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None
    else:
        status_in = [LibraryStatus.ACCEPTED]

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(type_in) == 0:
            type_in = None
    
    libraries, n_pages = db.get_libraries(
        sort_by=sort_by, descending=descending, offset=offset,
        seq_request_id=seq_request_id, status_in=status_in, type_in=type_in
    )
    return make_response(
        render_template(
            "workflows/library_pooling/select-libraries-table.html",
            libraries=libraries, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, seq_request_id=seq_request_id,
            status_in=status_in, type_in=type_in
        )
    )


@library_pooling_workflow.route("query_libraries", methods=["GET"])
@login_required
def query_libraries() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(type_in) == 0:
            type_in = None

    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)

    libraries: list[models.Library] = []
    if field_name == "name":
        libraries = db.query_libraries(word, status_in=status_in, type_in=type_in, seq_request_id=seq_request_id)
    elif field_name == "id":
        try:
            _id = int(word)
            if (library := db.get_library(_id)) is not None:
                libraries = [library]
                if status_in is not None and library.status not in status_in:
                    libraries = []
                if type_in is not None and library.type not in type_in:
                    libraries = []
                if seq_request_id is not None and library.seq_request_id != seq_request_id:
                    libraries = []
        except ValueError:
            pass
    
    return make_response(
        render_template(
            "workflows/library_pooling/select-libraries-table.html",
            current_query=word, active_query_field=field_name,
            libraries=libraries, type_in=type_in, status_in=status_in
        )
    )


@library_pooling_workflow.route("download_barcode_table_template/<string:uuid>", methods=["GET"])
@login_required
def download_barcode_table_template(uuid: str) -> Response:
    form = forms.BarcodeInputForm(uuid=uuid)
    template = form.get_template()

    pool_name = form.metadata.get("pool_name", "pool")

    return Response(
        template.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=pooling_{pool_name}.tsv"}
    )


@library_pooling_workflow.route("begin", methods=["GET"])
@login_required
def begin() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    seq_request_id = request.args.get("seq_request_id")
        
    form = forms.DefinePoolForm()
    form.prepare(current_user, seq_request_id=seq_request_id)
    return form.make_response()


@library_pooling_workflow.route("define_pool", methods=["POST"])
@login_required
def define_pool() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    form = forms.DefinePoolForm(formdata=request.form)
    return form.process_request()


@library_pooling_workflow.route("select_libraries", methods=["POST"])
@login_required
def select_libraries() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.SelectLibrariesForm(formdata=request.form)
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