import json
from typing import TYPE_CHECKING

import pandas as pd

from flask import Blueprint, render_template, request, abort, url_for, flash
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, db_session, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, IndexType, BarcodeType, KitType

from .... import db, logger, cache, forms  # noqa F401
from ....tools import SpreadSheetColumn

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user


index_kits_htmx = Blueprint("index_kits_htmx", __name__, url_prefix="/api/hmtx/index_kits/")


@index_kits_htmx.route("get", methods=["GET"], defaults={"page": 0})
@index_kits_htmx.route("get/<int:page>", methods=["GET"])
@db_session(db)
@login_required
@cache.cached(timeout=300, query_string=True)
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

    index_kits, n_pages = db.get_index_kits(offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending, type_in=type_in)

    return make_response(
        render_template(
            "components/tables/index_kit.html", index_kits=index_kits,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            type_in=type_in
        )
    )


@index_kits_htmx.route("table_query", methods=["GET"])
@db_session(db)
@login_required
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


@index_kits_htmx.route("<int:index_kit_id>/get_adapters", methods=["GET"], defaults={"page": 0})
@index_kits_htmx.route("<int:index_kit_id>/get_adapters/<int:page>", methods=["GET"])
@login_required
@cache.cached(timeout=300, query_string=True)
def get_adapters(index_kit_id: int, page: int):
    if (index_kit := db.get_index_kit(index_kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    adapters, n_pages = db.get_adapters(index_kit_id=index_kit_id, offset=offset, sort_by=sort_by, descending=descending)

    return make_response(
        render_template(
            "components/tables/index_kit-adapter.html", adapters=adapters,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            index_kit=index_kit
        )
    )


@index_kits_htmx.route("<int:index_kit_id>/render_table", methods=["GET"])
@db_session(db)
@login_required
@cache.cached(timeout=300, query_string=True)
def render_table(index_kit_id: int):
    if (index_kit := db.get_index_kit(index_kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    barcodes = db.get_index_kit_barcodes_df(index_kit_id)

    if index_kit.type == IndexType.TENX_ATAC_INDEX:
        barcode_data = {
            "well": [],
            "index_name": [],
            "sequence_1": [],
            "sequence_2": [],
            "sequence_3": [],
            "sequence_4": [],
        }
        for _, row in barcodes.iterrows():
            barcode_data["well"].append(row["well"])
            barcode_data["index_name"].append(row["names"][0])
            for i in range(4):
                barcode_data[f"sequence_{i + 1}"].append(row["sequences"][i])
    elif index_kit.type == IndexType.DUAL_INDEX:
        barcode_data = {
            "well": [],
            "index_name_i7": [],
            "sequence_i7": [],
            "index_name_i5": [],
            "sequence_i5": [],
        }
        for _, row in barcodes.iterrows():
            barcode_data["well"].append(row["well"])
            for i in range(2):
                if row["types"][i] == BarcodeType.INDEX_I7:
                    barcode_data["index_name_i7"].append(row["names"][i])
                    barcode_data["sequence_i7"].append(row["sequences"][i])
                else:
                    barcode_data["index_name_i5"].append(row["names"][i])
                    barcode_data["sequence_i5"].append(row["sequences"][i])
    elif index_kit.type == IndexType.SINGLE_INDEX:
        barcode_data = {
            "well": [],
            "index_name": [],
            "sequence_i7": [],
        }
        for _, row in barcodes.iterrows():
            barcode_data["well"].append(row["well"])
            barcode_data["index_name"].append(row["names"][0])
            barcode_data["sequence_i7"].append(row["sequences"][0])

    df = pd.DataFrame(barcode_data)

    columns = []
    for i, col in enumerate(df.columns):
        if "sequence" in col:
            width = 300
        elif "well" in col:
            width = 100
        else:
            width = 150
        columns.append(SpreadSheetColumn(col, col, "text", width, var_type=str))
    
    return make_response(
        render_template(
            "components/itable.html", index_kit=index_kit, columns=columns,
            spreadsheet_data=df.replace(pd.NA, "").values.tolist(),
            table_id=f"index_kit_table-{index_kit_id}"
        )
    )


@index_kits_htmx.route("get_form/<string:form_type>", methods=["GET"])
@db_session(db)
@login_required
def get_form(form_type: str):
    if not current_user.is_insider():
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


@index_kits_htmx.route("create", methods=["GET", "POST"])
@db_session(db)
@login_required
def create():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if request.method == "GET":
        return forms.models.IndexKitForm(form_type="create").make_response()
    elif request.method == "POST":
        form = forms.models.IndexKitForm(form_type="create", formdata=request.form)
        return form.process_request()
    else:
        return abort(HTTPResponse.METHOD_NOT_ALLOWED.id)


@index_kits_htmx.route("edit/<int:index_kit_id>", methods=["GET", "POST"])
@db_session(db)
@login_required
def edit(index_kit_id: int):
    if not current_user.is_insider():
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


@index_kits_htmx.route("delete/<int:index_kit_id>", methods=["DELETE"])
@db_session(db)
@login_required
def delete(index_kit_id: int):
    if not current_user.is_admin():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (_ := db.get_index_kit(index_kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    db.delete_index_kit(id=index_kit_id)
    flash("Index kit deleted successfully.", "success")
    return make_response(redirect=url_for("kits_page.index_kits_page"))


@index_kits_htmx.route("<int:index_kit_id>/edit_barcodes", methods=["GET", "POST"])
@db_session(db)
@login_required
def edit_barcodes(index_kit_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (index_kit := db.get_index_kit(index_kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if request.method == "GET":
        return forms.EditKitBarcodesForm(index_kit=index_kit).make_response()
    elif request.method == "POST":
        form = forms.EditKitBarcodesForm(
            index_kit=index_kit,
            formdata=request.form
        )
        return form.process_request()
    
    return abort(HTTPResponse.METHOD_NOT_ALLOWED.id)