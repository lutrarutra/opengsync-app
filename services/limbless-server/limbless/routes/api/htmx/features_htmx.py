import os
from typing import Optional, TYPE_CHECKING

from flask import Blueprint, render_template, request, abort, current_app
from flask_htmx import make_response
from flask_login import login_required

from .... import db, logger, forms, models, PAGE_LIMIT
from ....core import DBSession
from ....categories import LibraryType, HttpResponse

if TYPE_CHECKING:
    current_user: models.User = None
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
            features, n_pages = session.get_features(feature_kit_id=feature_kit_id, limit=PAGE_LIMIT, offset=offset, sort_by=sort_by, descending=descending)
        
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