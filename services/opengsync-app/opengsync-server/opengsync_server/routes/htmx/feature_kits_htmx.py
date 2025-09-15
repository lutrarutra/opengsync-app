import pandas as pd

from flask import Blueprint, render_template, request, flash, url_for
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import KitType

from ... import db
from ...core import wrappers, exceptions
from ... import forms
from ...tools.spread_sheet_components import TextColumn

feature_kits_htmx = Blueprint("feature_kits_htmx", __name__, url_prefix="/hmtx/feature_kits/")


@wrappers.htmx_route(feature_kits_htmx, db=db, cache_timeout_seconds=60, cache_type="global")
def get(page: int = 0):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if sort_by not in models.FeatureKit.sortable_fields:
        raise exceptions.BadRequestException()

    feature_kits, n_pages = db.feature_kits.find(
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


@wrappers.htmx_route(feature_kits_htmx, db=db, methods=["POST"])
def query():
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name, default="")) is None:
        raise exceptions.BadRequestException()

    if (word := request.form.get(field_name)) is None:
        raise exceptions.BadRequestException()

    results = db.kits.query(word, kit_type=KitType.FEATURE_KIT)

    return make_response(
        render_template(
            "components/search/feature_kit.html",
            results=results,
            field_name=field_name
        )
    )


@wrappers.htmx_route(feature_kits_htmx, db=db)
def table_query(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        raise exceptions.BadRequestException()

    feature_kits = []
    if field_name == "name":
        feature_kits = db.kits.query(word, kit_type=KitType.FEATURE_KIT)
    elif field_name == "id":
        try:
            _id = int(word)
        except ValueError:
            raise exceptions.BadRequestException()

        if (feature_kit := db.feature_kits.get(_id)) is not None:
            feature_kits.append(feature_kit)
    else:
        raise exceptions.BadRequestException()

    return make_response(
        render_template(
            "components/tables/feature_kit.html",
            feature_kits=feature_kits, current_query=word
        )
    )


@wrappers.htmx_route(feature_kits_htmx, db=db, cache_timeout_seconds=60, cache_type="global")
def get_features(feature_kit_id: int, page: int = 0):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Feature.sortable_fields:
        raise exceptions.BadRequestException()
        
    feature_kit = db.feature_kits.get(feature_kit_id)
    features, n_pages = db.features.find(feature_kit_id=feature_kit_id, offset=offset, sort_by=sort_by, descending=descending, count_pages=True)
    
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


@wrappers.htmx_route(feature_kits_htmx, db=db, methods=["GET", "POST"])
def create(current_user: models.User):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        return forms.models.FeatureKitForm(form_type="create").make_response()
    elif request.method == "POST":
        form = forms.models.FeatureKitForm(form_type="create", formdata=request.form)
        return form.process_request()
    else:
        raise exceptions.MethodNotAllowedException()


@wrappers.htmx_route(feature_kits_htmx, db=db, methods=["GET", "POST"])
def edit(current_user: models.User, feature_kit_id: int):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    if (feature_kit := db.feature_kits.get(feature_kit_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        return forms.models.FeatureKitForm(form_type="edit", feature_kit=feature_kit).make_response()
    elif request.method == "POST":
        form = forms.models.FeatureKitForm(form_type="edit", formdata=request.form, feature_kit=feature_kit)
        return form.process_request()
    else:
        raise exceptions.MethodNotAllowedException()
    

@wrappers.htmx_route(feature_kits_htmx, db=db, methods=["GET", "POST"])
def edit_features(current_user: models.User, feature_kit_id: int):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if (feature_kit := db.feature_kits.get(feature_kit_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        return forms.EditKitFeaturesForm(feature_kit=feature_kit).make_response()
    elif request.method == "POST":
        form = forms.EditKitFeaturesForm(
            feature_kit=feature_kit,
            formdata=request.form
        )
        return form.process_request()
    
    raise exceptions.MethodNotAllowedException()


@wrappers.htmx_route(feature_kits_htmx, db=db, methods=["DELETE"])
def delete(current_user: models.User, feature_kit_id: int):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if (kit := db.feature_kits.get(feature_kit_id)) is None:
        raise exceptions.NotFoundException()
    
    db.feature_kits.delete(kit)

    flash("Index kit deleted successfully.", "success")
    return make_response(redirect=url_for("kits_page.feature_kits"))


@wrappers.htmx_route(feature_kits_htmx, db=db)
def render_table(feature_kit_id: int):
    if (feature_kit := db.feature_kits.get(feature_kit_id)) is None:
        raise exceptions.NotFoundException()
    
    df = db.pd.get_feature_kit_features(feature_kit_id=feature_kit.id)
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
