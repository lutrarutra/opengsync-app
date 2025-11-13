import json

from flask import Blueprint, render_template, request, url_for, flash
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import IndexType, KitType

from ... import db, forms, logger
from ...core import wrappers, exceptions


kits_htmx = Blueprint("kits_htmx", __name__, url_prefix="/htmx/kits/")


@wrappers.htmx_route(kits_htmx, db=db, cache_timeout_seconds=60, cache_type="global")
def get(page: int = 0):
    sort_by = request.args.get("sort_by", "identifier")
    sort_order = request.args.get("sort_order", "asc")
    descending = sort_order == "desc"

    if sort_by not in models.IndexKit.sortable_fields:
        raise exceptions.BadRequestException()
    
    if (type_in := request.args.get("kit_type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [KitType.get(int(status)) for status in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    kits, n_pages = db.kits.find(offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending, count_pages=True, type_in=type_in)

    return make_response(
        render_template(
            "components/tables/kit.html", kits=kits,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            type_in=type_in
        )
    )


@wrappers.htmx_route(kits_htmx, db=db)
def table_query():
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    elif (word := request.args.get("identifier")) is not None:
        field_name = "identifier"
    else:
        raise exceptions.BadRequestException()
    
    if (type_in := request.args.get("kit_type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [KitType.get(int(status)) for status in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None
    
    kits: list[models.Kit] = []
    if field_name == "id":
        try:
            _id = int(word)
            if (kit := db.kits.get(_id)) is not None:
                if type_in is None or kit.kit_type in type_in:
                    kits.append(kit)

        except ValueError:
            pass
    elif field_name in ["name", "identifier"]:
        kits = db.kits.query(word)

    return make_response(
        render_template(
            "components/tables/kit.html", kits=kits,
            active_query_field=field_name, current_query=word, type_in=type_in
        )
    )


@wrappers.htmx_route(kits_htmx, db=db, methods=["GET", "POST"])
def edit(current_user: models.User, kit_id: int):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    if (index_kit := db.kits.get(kit_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        return forms.models.KitForm(form_type="edit", kit=index_kit).make_response()
    elif request.method == "POST":
        form = forms.models.KitForm(form_type="edit", formdata=request.form, kit=index_kit)
        return form.process_request()
    else:
        raise exceptions.MethodNotAllowedException()


@wrappers.htmx_route(kits_htmx, db=db, methods=["DELETE"])
def delete(current_user: models.User, kit_id: int):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if (kit := db.kits.get(kit_id)) is None:
        raise exceptions.NotFoundException()
    
    db.kits.delete(kit)
    
    flash("Index kit deleted successfully.", "success")
    return make_response(redirect=url_for("kits_page.kits"))


@wrappers.htmx_route(kits_htmx, db=db, arg_params=["protocol_id"])
def browse(current_user: models.User, workflow: str, page: int = 0, protocol_id: int | None = None):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    context: dict = {"workflow": workflow}

    if (type_in := request.args.get("kit_type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [KitType.get(int(status)) for status in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    protocol = None
    if workflow == "add_kits_to_protocol":
        if protocol_id is None:
            raise exceptions.BadRequestException()
        if (protocol := db.protocols.get(protocol_id)) is None:
            raise exceptions.NotFoundException()
        context["protocol_id"] = protocol_id

    kits, n_pages = db.kits.find(
        offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending,
        count_pages=True, type_in=type_in,
        not_in_protocol=protocol if (protocol is not None and workflow == "add_kits_to_protocol") else None
    )

    return make_response(
        render_template(
            "components/tables/select-kits.html",
            kits=kits, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            context=context, type_in=type_in,
            workflow=workflow,
        )
    )


@wrappers.htmx_route(kits_htmx, db=db)
def browse_query(current_user: models.User, workflow: str, protocol_id: int | None = None):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    context: dict = {"workflow": workflow}
    
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    elif (word := request.args.get("identifier")) is not None:
        field_name = "identifier"
    else:
        raise exceptions.BadRequestException()
    
    if (type_in := request.args.get("kit_type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [KitType.get(int(status)) for status in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None
    
    kits: list[models.Kit] = []
    if field_name == "id":
        try:
            _id = int(word)
            if (kit := db.kits.get(_id)) is not None:
                if type_in is None or kit.kit_type in type_in:
                    kits.append(kit)

        except ValueError:
            pass
    elif field_name in ["name", "identifier"]:
        kits = db.kits.query(word)

    return make_response(
        render_template(
            "components/tables/select-kits.html",
            kits=kits, context=context,
            active_query_field=field_name, current_query=word,
            type_in=type_in
        )
    )