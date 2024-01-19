from typing import Optional, TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from .... import db, logger, forms, models, PAGE_LIMIT
from ....core import DBSession
from ....categories import LibraryType, HttpResponse

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user

barcodes_htmx = Blueprint("barcodes_htmx", __name__, url_prefix="/api/barcodes/")


@barcodes_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"

    if sort_by not in models.Barcode.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    with DBSession(db.db_handler) as session:
        barcodes, n_pages = session.get_seqbarcodes(limit=PAGE_LIMIT, offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending)

    return make_response(
        render_template(
            "components/tables/barcode.html", barcodes=barcodes,
            barcodes_n_pages=n_pages, barcodes_active_page=page,
            barcodes_current_sort=sort_by, barcodes_current_sort_order=order
        ), push_url=False
    )


@barcodes_htmx.route("query_index_kits", methods=["POST"])
@login_required
def query_index_kits():
    field_name = next(iter(request.form.keys()))
    word = request.form.get(field_name)

    if word is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    results = db.db_handler.query_index_kit(word)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        ), push_url=False
    )


@barcodes_htmx.route("query/<int:index_kit_id>", methods=["POST"], defaults={"exclude_library_id": None})
@barcodes_htmx.route("query_adapters/<int:index_kit_id>/<int:exclude_library_id>", methods=["POST"])
@login_required
def query_adapters(index_kit_id: int, exclude_library_id: Optional[int] = None):
    field_name = next(iter(request.form.keys()))
    
    if (word := request.form.get(field_name)) is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    # TODO: add exclude_library_id to query_adapters
    results = db.db_handler.query_adapters(
        word, index_kit_id=index_kit_id
    )

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        ), push_url=False
    )