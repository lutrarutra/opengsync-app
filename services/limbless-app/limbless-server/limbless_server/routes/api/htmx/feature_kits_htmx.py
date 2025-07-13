from typing import TYPE_CHECKING

import pandas as pd

from flask import Blueprint, render_template, request, abort, flash, url_for
from flask_htmx import make_response
from flask_login import login_required

from opengsync_db import models, PAGE_LIMIT, db_session
from opengsync_db.categories import HTTPResponse, KitType

from .... import db, logger, cache  # noqa: F401
from .... import forms
from ....tools.spread_sheet_components import TextColumn

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

feature_kits_htmx = Blueprint("feature_kits_htmx", __name__, url_prefix="/api/hmtx/feature_kits/")


@feature_kits_htmx.route("get", methods=["GET"], defaults={"page": 0})
@feature_kits_htmx.route("get/<int:page>", methods=["GET"])
@db_session(db)
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if sort_by not in models.FeatureKit.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)

    feature_kits, n_pages = db.get_feature_kits(
        offset=PAGE_LIMIT * page,
        sort_by=sort_by, descending=descending, count_pages=True
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

    results = db.query_kits(word, kit_type=KitType.FEATURE_KIT)

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
        feature_kits = db.query_kits(word, kit_type=KitType.FEATURE_KIT)
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
@cache.cached(timeout=300, query_string=True)
def get_features(feature_kit_id: int, page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Feature.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)
        
    feature_kit = db.get_feature_kit(feature_kit_id)
    features, n_pages = db.get_features(feature_kit_id=feature_kit_id, offset=offset, sort_by=sort_by, descending=descending, count_pages=True)
    
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


@feature_kits_htmx.route("create", methods=["GET", "POST"])
@db_session(db)
@login_required
def create():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if request.method == "GET":
        return forms.models.FeatureKitForm(form_type="create").make_response()
    elif request.method == "POST":
        form = forms.models.FeatureKitForm(form_type="create", formdata=request.form)
        return form.process_request()
    else:
        return abort(HTTPResponse.METHOD_NOT_ALLOWED.id)


@feature_kits_htmx.route("edit/<int:feature_kit_id>", methods=["GET", "POST"])
@db_session(db)
@login_required
def edit(feature_kit_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    if (feature_kit := db.get_feature_kit(feature_kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if request.method == "GET":
        return forms.models.FeatureKitForm(form_type="edit", feature_kit=feature_kit).make_response()
    elif request.method == "POST":
        form = forms.models.FeatureKitForm(form_type="edit", formdata=request.form, feature_kit=feature_kit)
        return form.process_request()
    else:
        return abort(HTTPResponse.METHOD_NOT_ALLOWED.id)
    

@feature_kits_htmx.route("<int:feature_kit_id>/edit_features", methods=["GET", "POST"])
@db_session(db)
@login_required
def edit_features(feature_kit_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (feature_kit := db.get_feature_kit(feature_kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if request.method == "GET":
        return forms.EditKitFeaturesForm(feature_kit=feature_kit).make_response()
    elif request.method == "POST":
        form = forms.EditKitFeaturesForm(
            feature_kit=feature_kit,
            formdata=request.form
        )
        return form.process_request()
    
    return abort(HTTPResponse.METHOD_NOT_ALLOWED.id)


@feature_kits_htmx.route("delete/<int:feature_kit_id>", methods=["DELETE"])
@db_session(db)
@login_required
def delete(feature_kit_id: int):
    if not current_user.is_admin():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (_ := db.get_feature_kit(feature_kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    db.delete_kit(id=feature_kit_id)
    flash("Index kit deleted successfully.", "success")
    return make_response(redirect=url_for("kits_page.feature_kits_page"))


@feature_kits_htmx.route("<int:feature_kit_id>/render_table", methods=["GET"])
@db_session(db)
@login_required
def render_table(feature_kit_id: int):
    if (feature_kit := db.get_feature_kit(feature_kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    df = db.get_feature_kit_features_df(feature_kit_id=feature_kit.id)
    df = df.drop(columns=["type", "type_id"])

    columns = []
    for i, col in enumerate(df.columns):
        if col == "feature_id":
            width = 50
        elif col == "read":
            width = 50
        else:
            width = 200
        columns.append(TextColumn(col, col.replace("_", " ").title().replace("Id", "ID"), width, max_length=1000))
    
    return make_response(
        render_template(
            "components/itable.html", feature_kit=feature_kit, columns=columns,
            spreadsheet_data=df.replace(pd.NA, "").values.tolist(),
            table_id=f"feature_kit_table-{feature_kit_id}"
        )
    )
