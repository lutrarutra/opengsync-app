import json

import pandas as pd

from flask import Blueprint, render_template, request
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import IndexType, KitType

from ... import db, logger, forms
from ...core import wrappers, exceptions
from ...tools.spread_sheet_components import TextColumn
from ...tools import StaticSpreadSheet

index_kits_htmx = Blueprint("index_kits_htmx", __name__, url_prefix="/htmx/index_kits/")


@wrappers.htmx_route(index_kits_htmx, db=db)
def get(page: int = 0):
    sort_by = request.args.get("sort_by", "identifier")
    sort_order = request.args.get("sort_order", "asc")
    descending = sort_order == "desc"

    if sort_by not in models.IndexKit.sortable_fields:
        raise exceptions.BadRequestException()
    
    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [IndexType.get(int(status)) for status in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    index_kits, n_pages = db.index_kits.find(offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending, type_in=type_in, count_pages=True)

    return make_response(
        render_template(
            "components/tables/index_kit.html", index_kits=index_kits,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            type_in=type_in
        )
    )


@wrappers.htmx_route(index_kits_htmx, db=db, methods=["POST"])
def query():
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name, default="")) is None:
        raise exceptions.BadRequestException()
            
    results = db.index_kits.query(word)

    return make_response(
        render_template(
            "components/search/index_kit.html",
            results=results,
            field_name=field_name
        )
    )


@wrappers.htmx_route(index_kits_htmx, db=db)
def table_query():
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    elif (word := request.args.get("identifier")) is not None:
        field_name = "identifier"
    else:
        raise exceptions.BadRequestException()
    
    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [IndexType.get(int(status)) for status in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None
    
    index_kits: list[models.Kit] = []
    if field_name == "id":
        try:
            _id = int(word)
            if (index_kit := db.index_kits.get(_id)) is not None:
                if type_in is None or index_kit.type in type_in:
                    index_kits.append(index_kit)

        except ValueError:
            pass
    elif field_name in ["name", "identifier"]:
        index_kits = db.kits.query(word, kit_type=KitType.INDEX_KIT)

    return make_response(
        render_template(
            "components/tables/index_kit.html", index_kits=index_kits,
            active_query_field=field_name, current_query=word, type_in=type_in
        )
    )


@wrappers.htmx_route(index_kits_htmx, db=db, cache_timeout_seconds=60, cache_type="global")
def get_adapters(index_kit_id: int, page: int = 0):
    if (index_kit := db.index_kits.get(index_kit_id)) is None:
        raise exceptions.NotFoundException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    adapters, n_pages = db.adapters.find(index_kit_id=index_kit_id, offset=offset, sort_by=sort_by, descending=descending, count_pages=True)

    return make_response(
        render_template(
            "components/tables/index_kit-adapter.html", adapters=adapters,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            index_kit=index_kit
        )
    )


@wrappers.htmx_route(index_kits_htmx, db=db)
def render_table(index_kit_id: int):
    if (index_kit := db.index_kits.get(index_kit_id)) is None:
        raise exceptions.NotFoundException()
    
    df = db.pd.get_index_kit_barcodes(index_kit_id, per_index=True)
    df = df.drop(columns=["adapter_id"])

    columns = []
    for i, col in enumerate(df.columns):
        if "sequence" in col:
            width = 200
        elif "well" in col:
            width = 100
        else:
            width = 150
        columns.append(TextColumn(col, col, width, max_length=1000))

    spreadsheet = StaticSpreadSheet(df, columns=columns, id=f"index_kit_table-{index_kit_id}")

    return make_response(render_template("components/itable.html", spreadsheet=spreadsheet))


@wrappers.htmx_route(index_kits_htmx, db=db)
def get_form(current_user: models.User, form_type: str):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    if form_type == "edit":
        if (index_kit_id := request.args.get("index_kit_id")) is None:
            raise exceptions.BadRequestException()
        try:
            index_kit_id = int(index_kit_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (index_kit := db.index_kits.get(index_kit_id)) is None:
            raise exceptions.NotFoundException()
    elif form_type == "create":
        index_kit = None
    else:
        raise exceptions.BadRequestException()
    
    return forms.models.IndexKitForm(
        form_type=form_type,
        index_kit=index_kit
    ).make_response()


@wrappers.htmx_route(index_kits_htmx, db=db, methods=["GET", "POST"])
def create(current_user: models.User):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        return forms.models.IndexKitForm(form_type="create").make_response()
    elif request.method == "POST":
        form = forms.models.IndexKitForm(form_type="create", formdata=request.form)
        return form.process_request()
    else:
        raise exceptions.MethodNotAllowedException()


@wrappers.htmx_route(index_kits_htmx, db=db, methods=["GET", "POST"])
def edit(current_user: models.User, index_kit_id: int):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    if (index_kit := db.index_kits.get(index_kit_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        return forms.models.IndexKitForm(form_type="edit", index_kit=index_kit).make_response()
    elif request.method == "POST":
        form = forms.models.IndexKitForm(form_type="edit", formdata=request.form, index_kit=index_kit)
        return form.process_request()
    else:
        raise exceptions.MethodNotAllowedException()


@wrappers.htmx_route(index_kits_htmx, db=db, methods=["GET", "POST"])
def edit_barcodes(current_user: models.User, index_kit_id: int):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if (index_kit := db.index_kits.get(index_kit_id)) is None:
        raise exceptions.NotFoundException()
    
    match index_kit.type:
        case IndexType.TENX_ATAC_INDEX:
            cls = forms.workflows.edit_kit_barcodes.EditKitTENXATACBarcodesForm
        case IndexType.DUAL_INDEX:
            cls = forms.workflows.edit_kit_barcodes.EditDualIndexKitBarcodesForm
        case IndexType.SINGLE_INDEX_I7:
            cls = forms.workflows.edit_kit_barcodes.EditSingleIndexKitBarcodesForm
        case IndexType.COMBINATORIAL_DUAL_INDEX:
            cls = forms.workflows.edit_kit_barcodes.EditCombinatorialKitBarcodesForm
        case _:
            logger.error(f"Unknown index kit type {index_kit.type}")
            raise exceptions.BadRequestException()
    
    if request.method == "GET":
        return cls(index_kit=index_kit).make_response()
    elif request.method == "POST":
        form = cls(
            index_kit=index_kit,
            formdata=request.form
        )
        return form.process_request()
    
    raise exceptions.MethodNotAllowedException()