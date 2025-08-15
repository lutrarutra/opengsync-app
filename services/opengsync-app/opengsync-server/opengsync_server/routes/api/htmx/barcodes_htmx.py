from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response

from opengsync_db import PAGE_LIMIT
from opengsync_db.categories import HTTPResponse, IndexType

from .... import db, forms
from ....core import wrappers
barcodes_htmx = Blueprint("barcodes_htmx", __name__, url_prefix="/api/hmtx/barcodes/")


@wrappers.htmx_route(barcodes_htmx, db=db, cache_timeout_seconds=60, cache_type="global")
def get(page: int = 0):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    barcodes, n_pages = db.barcodes.find(offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending, count_pages=True)

    return make_response(
        render_template(
            "components/tables/barcode.html", barcodes=barcodes,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order
        )
    )


@wrappers.htmx_route(barcodes_htmx, "query_index_kits", db=db, methods=["POST"])
def query_index_kits():
    field_name = next(iter(request.form.keys()))

    if (index_type_id_in := request.args.get("index_type_id_in")) is not None:
        try:
            index_type_in = [IndexType.get(int(i)) for i in index_type_id_in.split(",")]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    else:
        index_type_in = None
    
    if (word := request.form.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    results = db.index_kits.query(word, index_type_in=index_type_in)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        )
    )


@wrappers.htmx_route(barcodes_htmx, "query_barcode_sequences", db=db, methods=["GET", "POST"])
def query_barcode_sequences():
    if request.method == "GET":
        form = forms.QueryBarcodeSequencesForm()
        return form.make_response()
    
    form = forms.QueryBarcodeSequencesForm(formdata=request.form)
    return form.process_request()