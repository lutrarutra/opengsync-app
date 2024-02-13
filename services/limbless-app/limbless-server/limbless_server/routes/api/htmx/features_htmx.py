from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT
from limbless_db.core.categories import HttpResponse
from .... import db

if TYPE_CHECKING:
    current_user: models.User = None   # type: ignore
else:
    from flask_login import current_user


features_htmx = Blueprint("features_htmx", __name__, url_prefix="/api/features/")


@features_htmx.route("get_kit/<int:page>", methods=["GET"])
@login_required
def get_kit(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"

    raise NotImplementedError()


@features_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Feature.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    features: list[models.Feature] = []
    context = {}

    if (feature_kit_id := request.args.get("feature_kit_id")) is not None:
        template = "components/tables/feature_kit-feature.html"
        try:
            feature_kit_id = int(feature_kit_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        with DBSession(db.db_handler) as session:
            feature_kit = session.get_feature_kit(feature_kit_id)
            features, n_pages = session.get_features(feature_kit_id=feature_kit_id, offset=offset, sort_by=sort_by, descending=descending)
        
        context["feature_kit"] = feature_kit

    else:
        raise NotImplementedError()
    
    return make_response(
        render_template(
            template, features=features,
            features_current_sort=sort_by,
            features_current_sort_order=order,
            features_n_pages=n_pages,
            features_active_page=page,
            **context
        )
    )


@features_htmx.route("query_kits", methods=["POST"])
@login_required
def query_kits():
    field_name = next(iter(request.form.keys()))

    if (word := request.form.get(field_name)) is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    results = db.db_handler.query_feature_kits(word)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        ), push_url=False
    )