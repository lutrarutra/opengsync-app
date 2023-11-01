from typing import Optional

from flask import Blueprint, render_template, request, abort, url_for
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, logger, forms, models
from ....core import DBSession
from ....categories import HttpResponse

adapters_htmx = Blueprint("adapters_htmx", __name__, url_prefix="/api/adapters/")


@adapters_htmx.route("<index_kit_id>/get/<int:page>", methods=["GET"], defaults={"index_kit_id": None})
@adapters_htmx.route("<int:index_kit_id>/get/<int:page>", methods=["GET"])
@login_required
def get(page: int, index_kit_id: Optional[int]):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    reversed = order == "desc"
    offset = page * 20

    if sort_by not in models.SeqAdapter.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    with DBSession(db.db_handler) as session:
        if index_kit_id is not None:
            index_kit = session.get_index_kit(index_kit_id)
            if index_kit is None:
                return abort(HttpResponse.NOT_FOUND.value.id)

        adapters, n_pages = session.get_adapters(index_kit_id=index_kit_id, offset=offset, sort_by=sort_by, reversed=reversed)

    return make_response(
        render_template(
            "components/tables/adapter.html", adapters=adapters,
            n_pages=n_pages, active_page=page, index_kit_id=index_kit_id,
            current_sort=sort_by, current_sort_order=order
        ), push_url=False
    )