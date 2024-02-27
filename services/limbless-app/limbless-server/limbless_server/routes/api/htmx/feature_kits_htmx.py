from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT
from limbless_db.core.categories import HttpResponse
from .... import db, logger

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

feature_kits_htmx = Blueprint("feature_kits_htmx", __name__, url_prefix="/api/feature_kits/")


@feature_kits_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"

    if sort_by not in models.FeatureKit.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.id)

    with DBSession(db) as session:
        feature_kits, n_pages = session.get_feature_kits(
            offset=PAGE_LIMIT * page,
            sort_by=sort_by, descending=descending
        )

    return make_response(
        render_template(
            "components/tables/feature_kit.html",
            feature_kits=feature_kits,
            feature_kits_n_pages=n_pages, feature_kits_active_page=page,
            feature_kits_current_sort=sort_by, feature_kits_current_sort_order=order
        ), push_url=False
    )


@feature_kits_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name, default="")) is None:
        return abort(HttpResponse.BAD_REQUEST.id)

    if (word := request.form.get(field_name)) is None:
        return abort(HttpResponse.BAD_REQUEST.id)

    results = db.query_feature_kits(word)
    logger.debug(word)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        ), push_url=False
    )