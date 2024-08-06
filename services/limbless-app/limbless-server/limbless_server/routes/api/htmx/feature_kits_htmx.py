from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT
from limbless_db.categories import HTTPResponse
from .... import db, logger  # noqa: F401

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

feature_kits_htmx = Blueprint("feature_kits_htmx", __name__, url_prefix="/api/hmtx/feature_kits/")


@feature_kits_htmx.route("get", methods=["GET"], defaults={"page": 0})
@feature_kits_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if sort_by not in models.FeatureKit.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)

    with DBSession(db) as session:
        feature_kits, n_pages = session.get_feature_kits(
            offset=PAGE_LIMIT * page,
            sort_by=sort_by, descending=descending
        )

    return make_response(
        render_template(
            "components/tables/feature_kit.html",
            feature_kits=feature_kits,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order
        )
    )


@feature_kits_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name, default="")) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if (word := request.form.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    results = db.query_feature_kits(word)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        )
    )


@feature_kits_htmx.route("table_query", methods=["GET"])
@login_required
def table_query():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)

    feature_kits = []
    if field_name == "name":
        feature_kits = db.query_feature_kits(word)
    elif field_name == "id":
        try:
            _id = int(word)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)

        if (feature_kit := db.get_feature_kit(_id)) is not None:
            feature_kits.append(feature_kit)
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)

    return make_response(
        render_template(
            "components/tables/feature_kit.html",
            feature_kits=feature_kits, current_query=word
        )
    )


@feature_kits_htmx.route("<int:feature_kit_id>/get_features", methods=["GET"], defaults={"page": 0})
@feature_kits_htmx.route("<int:feature_kit_id>/get_features/<int:page>", methods=["GET"])
@login_required
def get_features(feature_kit_id: int, page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Feature.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)
        
    feature_kit = db.get_feature_kit(feature_kit_id)
    features, n_pages = db.get_features(feature_kit_id=feature_kit_id, offset=offset, sort_by=sort_by, descending=descending)
    
    return make_response(
        render_template(
            "components/tables/feature_kit-feature.html",
            features=features, feature_kit=feature_kit,
            sort_by=sort_by,
            sort_order=sort_order,
            n_pages=n_pages,
            active_page=page,
        )
    )
