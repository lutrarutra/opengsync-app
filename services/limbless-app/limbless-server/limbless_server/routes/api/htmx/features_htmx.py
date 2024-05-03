from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT
from limbless_db.categories import HTTPResponse
from .... import db

if TYPE_CHECKING:
    current_user: models.User = None   # type: ignore
else:
    from flask_login import current_user


features_htmx = Blueprint("features_htmx", __name__, url_prefix="/api/hmtx/features/")


@features_htmx.route("get_kit/<int:page>", methods=["GET"])
@login_required
def get_kit(page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    raise NotImplementedError()


@features_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Feature.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    features: list[models.Feature] = []
    context = {}

    if (feature_kit_id := request.args.get("feature_kit_id")) is not None:
        template = "components/tables/feature_kit-feature.html"
        try:
            feature_kit_id = int(feature_kit_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        with DBSession(db) as session:
            feature_kit = session.get_feature_kit(feature_kit_id)
            features, n_pages = session.get_features(feature_kit_id=feature_kit_id, offset=offset, sort_by=sort_by, descending=descending)
        
        context["feature_kit"] = feature_kit
    elif (library_id := request.args.get("library_id")) is not None:
        template = "components/tables/library-feature.html"
        try:
            library_id = int(library_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        with DBSession(db) as session:
            library = session.get_library(library_id)
            features, n_pages = session.get_features(library_id=library_id, offset=offset, sort_by=sort_by, descending=descending)
        
        context["library"] = library
    else:
        raise NotImplementedError()
    
    return make_response(
        render_template(
            template, features=features,
            sort_by=sort_by,
            sort_order=sort_order,
            n_pages=n_pages,
            active_page=page,
            **context
        )
    )