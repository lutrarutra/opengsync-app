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

adapters_htmx = Blueprint("adapters_htmx", __name__, url_prefix="/api/hmtx/adapters/")


@adapters_htmx.route("get", methods=["GET"], defaults={"index_kit_id": None, "page": 0})
@adapters_htmx.route("<int:index_kit_id>/get", methods=["GET"], defaults={"page": 0})
@adapters_htmx.route("get/<int:page>", methods=["GET"], defaults={"index_kit_id": None})
@adapters_htmx.route("<int:index_kit_id>/get/<int:page>", methods=["GET"])
@login_required
def get(page: int, index_kit_id: Optional[int]):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Adapter.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)

    with DBSession(db) as session:
        if index_kit_id is not None:
            if (index_kit := session.get_index_kit(index_kit_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)

        adapters, n_pages = session.get_adapters(index_kit_id=index_kit_id, offset=offset, sort_by=sort_by, descending=descending)

    return make_response(
        render_template(
            "components/tables/adapter.html", adapters=adapters,
            n_pages=n_pages, active_page=page, index_kit=index_kit,
            sort_by=sort_by, sort_order=sort_order
        )
    )