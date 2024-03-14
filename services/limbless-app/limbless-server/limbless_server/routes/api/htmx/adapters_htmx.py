from typing import Optional, TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT
from limbless_db.categories import HTTPResponse
from .... import db

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

adapters_htmx = Blueprint("adapters_htmx", __name__, url_prefix="/api/adapters/")


@adapters_htmx.route("<index_kit_id>/get/<int:page>", methods=["GET"], defaults={"index_kit_id": None})
@adapters_htmx.route("<int:index_kit_id>/get/<int:page>", methods=["GET"])
@login_required
def get(page: int, index_kit_id: Optional[int]):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Adapter.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)

    with DBSession(db) as session:
        if index_kit_id is not None:
            index_kit = session.get_index_kit(index_kit_id)
            if index_kit is None:
                return abort(HTTPResponse.NOT_FOUND.id)

        adapters, n_pages = session.get_adapters(index_kit_id=index_kit_id, offset=offset, sort_by=sort_by, descending=descending)

    return make_response(
        render_template(
            "components/tables/adapter.html", adapters=adapters,
            adapters_n_pages=n_pages, adapters_active_page=page, index_kit_id=index_kit_id,
            adapters_current_sort=sort_by, adapters_current_sort_order=order
        ), push_url=False
    )