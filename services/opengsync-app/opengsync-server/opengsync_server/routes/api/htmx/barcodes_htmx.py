from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from opengsync_db import models, PAGE_LIMIT, db_session
from opengsync_db.categories import HTTPResponse, KitType
from .... import db, logger, forms  # noqa

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

barcodes_htmx = Blueprint("barcodes_htmx", __name__, url_prefix="/api/hmtx/barcodes/")


@barcodes_htmx.route("get/<int:page>", methods=["GET"])
@db_session(db)
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    barcodes, n_pages = db.get_barcodes(offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending, count_pages=True)

    return make_response(
        render_template(
            "components/tables/barcode.html", barcodes=barcodes,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order
        )
    )


@barcodes_htmx.route("query_index_kits", methods=["POST"])
@db_session(db)
@login_required
def query_index_kits():
    field_name = next(iter(request.form.keys()))
    
    if (word := request.form.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    results = db.query_kits(word, kit_type=KitType.INDEX_KIT)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        )
    )


@barcodes_htmx.route("query_barcode_sequences", methods=["GET", "POST"])
@db_session(db)
@login_required
def query_barcode_sequences():
    if request.method == "GET":
        form = forms.QueryBarcodeSequencesForm()
        return form.make_response()
    
    form = forms.QueryBarcodeSequencesForm(formdata=request.form)
    return form.process_request()