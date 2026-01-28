from flask import Blueprint, render_template, request
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import IndexType

from ... import db, logger, forms, logic
from ...core import wrappers, exceptions
from ...tools.spread_sheet_components import TextColumn
from ...tools import StaticSpreadSheet

index_kits_htmx = Blueprint("index_kits_htmx", __name__, url_prefix="/htmx/index_kits/")


@wrappers.htmx_route(index_kits_htmx, db=db)
def get(current_user: models.User):
    context = logic.index_kit.get_table_context(current_user=current_user, request=request)
    return make_response(render_template(**context))


@wrappers.htmx_route(index_kits_htmx, db=db)
def search(current_user: models.User):
    context = logic.index_kit.get_search_context(current_user=current_user, request=request)
    return make_response(render_template(**context))


@wrappers.htmx_route(index_kits_htmx, db=db, cache_timeout_seconds=60, cache_type="global")
def get_adapters(current_user: models.User):
    context = logic.adapter.get_table_context(current_user=current_user, request=request)
    return make_response(render_template(**context))


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