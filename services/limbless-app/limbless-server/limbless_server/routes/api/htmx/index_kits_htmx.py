from typing import TYPE_CHECKING

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

index_kits_htmx = Blueprint("index_kits_htmx", __name__, url_prefix="/api/hmtx/index_kits/")


@index_kits_htmx.route("get", methods=["GET"], defaults={"page": 0})
@index_kits_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if sort_by not in models.IndexKit.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)

    with DBSession(db) as session:
        index_kits, n_pages = session.get_index_kits(offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending)

    return make_response(
        render_template(
            "components/tables/index_kit.html", index_kits=index_kits,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order
        )
    )


@index_kits_htmx.route("table_query", methods=["POST"])
@login_required
def table_query():
    raise NotImplementedError()