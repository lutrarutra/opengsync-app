import json
from typing import TYPE_CHECKING

import pandas as pd

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import HTTPResponse, IndexType, KitType

from .... import db, logger, cache, forms, htmx_route  # noqa F401
from ....tools.spread_sheet_components import TextColumn
from ....core import wrappers

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user


index_kits_htmx = Blueprint("index_kits_htmx", __name__, url_prefix="/api/hmtx/index_kits/")


@wrappers.htmx_route(index_kits_htmx, db=db, debug=True)
def get(page: int = 0):
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

    index_kits, n_pages = db.get_index_kits(offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending, type_in=type_in, count_pages=True)

    return make_response(
        render_template(
            "components/tables/index_kit.html", index_kits=index_kits,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            type_in=type_in
        )
    )


@htmx_route(index_kits_htmx, db=db)
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
            type_in = [IndexType.get(int(status)) for status in type_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(type_in) == 0:
            type_in = None
    
    index_kits: list[models.Kit] = []
    if field_name == "id":
        try:
            _id = int(word)
            if (index_kit := db.get_index_kit(_id)) is not None:
                if type_in is None or index_kit.type in type_in:
                    index_kits.append(index_kit)

        except ValueError:
            pass
    elif field_name in ["name", "identifier"]:
        index_kits = db.query_kits(word, kit_type=KitType.INDEX_KIT)

    return make_response(
        render_template(
            "components/tables/index_kit.html", index_kits=index_kits,
            active_query_field=field_name, current_query=word, type_in=type_in
        )
    )


@htmx_route(index_kits_htmx, db=db)
@cache.cached(timeout=300, query_string=True)
def get_adapters(index_kit_id: int, page: int = 0):
    if (index_kit := db.get_index_kit(index_kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    adapters, n_pages = db.get_adapters(index_kit_id=index_kit_id, offset=offset, sort_by=sort_by, descending=descending, count_pages=True)

    return make_response(
        render_template(
            "components/tables/index_kit-adapter.html", adapters=adapters,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            index_kit=index_kit
        )
    )


@htmx_route(index_kits_htmx, db=db)
def render_table(index_kit_id: int):
    if (index_kit := db.get_index_kit(index_kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    df = db.get_index_kit_barcodes_df(index_kit_id, per_index=True)

    columns = []
    for i, col in enumerate(df.columns):
        if "sequence" in col:
            width = 200
        elif "well" in col:
            width = 100
        else:
            width = 150
        columns.append(TextColumn(col, col, width, max_length=1000))
    
    return make_response(
        render_template(
            "components/itable.html", index_kit=index_kit, columns=columns,
            spreadsheet_data=df.replace(pd.NA, "").values.tolist(),
            table_id=f"index_kit_table-{index_kit_id}"
        )
    )


@htmx_route(index_kits_htmx, db=db)
def get_form(form_type: str):
    if not current_user.is_admin():
        return abort(HTTPResponse.FORBIDDEN.id)
    if form_type == "edit":
        if (index_kit_id := request.args.get("index_kit_id")) is None:
            return abort(HTTPResponse.BAD_REQUEST.id)
        try:
            index_kit_id = int(index_kit_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if (index_kit := db.get_index_kit(index_kit_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
    elif form_type == "create":
        index_kit = None
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    return forms.models.IndexKitForm(
        form_type=form_type,
        index_kit=index_kit
    ).make_response()


@htmx_route(index_kits_htmx, db=db, methods=["GET", "POST"])
def create():
    if not current_user.is_admin():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if request.method == "GET":
        return forms.models.IndexKitForm(form_type="create").make_response()
    elif request.method == "POST":
        form = forms.models.IndexKitForm(form_type="create", formdata=request.form)
        return form.process_request()
    else:
        return abort(HTTPResponse.METHOD_NOT_ALLOWED.id)


@htmx_route(index_kits_htmx, db=db, methods=["GET", "POST"])
def edit(index_kit_id: int):
    if not current_user.is_admin():
        return abort(HTTPResponse.FORBIDDEN.id)
    if (index_kit := db.get_index_kit(index_kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if request.method == "GET":
        return forms.models.IndexKitForm(form_type="edit", index_kit=index_kit).make_response()
    elif request.method == "POST":
        form = forms.models.IndexKitForm(form_type="edit", formdata=request.form, index_kit=index_kit)
        return form.process_request()
    else:
        return abort(HTTPResponse.METHOD_NOT_ALLOWED.id)


@htmx_route(index_kits_htmx, db=db, methods=["GET", "POST"])
def edit_barcodes(index_kit_id: int):
    if not current_user.is_admin():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (index_kit := db.get_index_kit(index_kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if index_kit.type == IndexType.TENX_ATAC_INDEX:
        cls = forms.EditKitTENXATACBarcodesForm
    elif index_kit.type == IndexType.DUAL_INDEX:
        cls = forms.EditDualIndexKitBarcodesForm
    elif index_kit.type == IndexType.SINGLE_INDEX:
        cls = forms.EditSingleIndexKitBarcodesForm
    else:
        logger.error(f"Unknown index kit type {index_kit.type}")
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if request.method == "GET":
        return cls(index_kit=index_kit).make_response()
    elif request.method == "POST":
        form = cls(
            index_kit=index_kit,
            formdata=request.form
        )
        return form.process_request()
    
    return abort(HTTPResponse.METHOD_NOT_ALLOWED.id)