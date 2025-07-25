import json
from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort, url_for, flash
from flask_htmx import make_response
from flask_login import login_required

from opengsync_db import models, db_session, PAGE_LIMIT
from opengsync_db.categories import HTTPResponse, IndexType, KitType
from .... import db, logger, cache, forms, htmx_route  # noqa F401

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user


kits_htmx = Blueprint("kits_htmx", __name__, url_prefix="/api/hmtx/kits/")


@kits_htmx.route("get", methods=["GET"], defaults={"page": 0})
@kits_htmx.route("get/<int:page>", methods=["GET"])
@db_session(db)
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "identifier")
    sort_order = request.args.get("sort_order", "asc")
    descending = sort_order == "desc"

    if sort_by not in models.IndexKit.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [IndexType.get(int(status)) for status in type_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(type_in) == 0:
            type_in = None

    kits, n_pages = db.get_kits(offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending, count_pages=True)

    return make_response(
        render_template(
            "components/tables/kit.html", kits=kits,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            type_in=type_in
        )
    )


@htmx_route(kits_htmx, db=db)
def table_query():
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    elif (word := request.args.get("identifier")) is not None:
        field_name = "identifier"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [KitType.get(int(status)) for status in type_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(type_in) == 0:
            type_in = None
    
    kits: list[models.Kit] = []
    if field_name == "id":
        try:
            _id = int(word)
            if (kit := db.get_kit(_id)) is not None:
                if type_in is None or kit.kit_type in type_in:
                    kits.append(kit)

        except ValueError:
            pass
    elif field_name in ["name", "identifier"]:
        kits = db.query_kits(word)

    return make_response(
        render_template(
            "components/tables/kit.html", kits=kits,
            active_query_field=field_name, current_query=word, type_in=type_in
        )
    )


@htmx_route(kits_htmx, db=db, methods=["GET", "POST"])
def edit(kit_id: int):
    if not current_user.is_admin():
        return abort(HTTPResponse.FORBIDDEN.id)
    if (index_kit := db.get_kit(kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if request.method == "GET":
        return forms.models.KitForm(form_type="edit", kit=index_kit).make_response()
    elif request.method == "POST":
        form = forms.models.KitForm(form_type="edit", formdata=request.form, kit=index_kit)
        return form.process_request()
    else:
        return abort(HTTPResponse.METHOD_NOT_ALLOWED.id)


@htmx_route(kits_htmx, db=db, methods=["DELETE"])
def delete(kit_id: int):
    if not current_user.is_admin():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (_ := db.get_kit(kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    db.delete_kit(id=kit_id)
    flash("Index kit deleted successfully.", "success")
    return make_response(redirect=url_for("kits_page.kits"))