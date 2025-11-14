import json

from flask import Blueprint, render_template, request, url_for, flash
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import IndexType, AssayType

from ... import db, forms, logger
from ...core import wrappers, exceptions


protocols_htmx = Blueprint("protocols_htmx", __name__, url_prefix="/htmx/protocols/")


@wrappers.htmx_route(protocols_htmx, db=db, cache_timeout_seconds=60, cache_type="global")
def get(page: int = 0):
    sort_by = request.args.get("sort_by", "name")
    sort_order = request.args.get("sort_order", "asc")
    descending = sort_order == "desc"

    if sort_by not in models.Protocol.sortable_fields:
        raise exceptions.BadRequestException()
    
    if (assay_type_in := request.args.get("assay_type_id_in")) is not None:
        assay_type_in = json.loads(assay_type_in)
        try:
            assay_type_in = [AssayType.get(int(id)) for id in assay_type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(assay_type_in) == 0:
            assay_type_in = None

    protocols, n_pages = db.protocols.find(offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending, count_pages=True, assay_type_in=assay_type_in)

    return make_response(
        render_template(
            "components/tables/protocol.html", protocols=protocols,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            assay_type_in=assay_type_in
        )
    )

@wrappers.htmx_route(protocols_htmx, db=db)
def table_query():
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        raise exceptions.BadRequestException()
    
    if (assay_type_in := request.args.get("assay_type_id_in")) is not None:
        assay_type_in = json.loads(assay_type_in)
        try:
            assay_type_in = [AssayType.get(int(status)) for status in assay_type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(assay_type_in) == 0:
            assay_type_in = None
    
    protocols: list[models.Protocol] = []
    if field_name == "id":
        try:
            _id = int(word)
            if (protocol := db.protocols.get(_id)) is not None:
                if assay_type_in is None or protocol.assay_type in assay_type_in:
                    protocols.append(protocol)

        except ValueError:
            pass
    elif field_name in ["name", "identifier"]:
        protocols = db.protocols.query(word)

    return make_response(
        render_template(
            "components/tables/protocol.html", protocols=protocols,
            active_query_field=field_name, current_query=word, assay_type_in=assay_type_in
        )
    )


@wrappers.htmx_route(protocols_htmx, db=db, methods=["GET", "POST"])
def create(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    form = forms.models.ProtocolForm(form_type="create", formdata=request.form)

    if request.method == "POST":
        return form.process_request()

    return form.make_response()

@wrappers.htmx_route(protocols_htmx, db=db, methods=["GET", "POST"])
def edit(current_user: models.User, protocol_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (protocol := db.protocols.get(protocol_id)) is None:
        raise exceptions.NotFoundException()

    form = forms.models.ProtocolForm(form_type="edit", formdata=request.form, protocol=protocol)

    if request.method == "POST":
        return form.process_request()

    return form.make_response()


@wrappers.htmx_route(protocols_htmx, db=db)
def get_kits(current_user: models.User, protocol_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (protocol := db.protocols.get(protocol_id)) is None:
        raise exceptions.NotFoundException()
    
    sort_by = request.args.get("sort_by", "name")
    sort_order = request.args.get("sort_order", "asc")
    descending = sort_order == "desc"

    if sort_by not in models.Protocol.sortable_fields:
        raise exceptions.BadRequestException()
    
    kits, _ = db.kits.find(protocol=protocol, count_pages=False, limit=None, sort_by=sort_by, descending=descending)

    return make_response(
        render_template(
            "components/tables/protocol-kit.html",
            protocol=protocol, kits=kits,
            sort_by=sort_by, sort_order=sort_order,
        )
    )

@wrappers.htmx_route(protocols_htmx, db=db, methods=["DELETE"])
def remove_kit(current_user: models.User, protocol_id: int, kit_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (protocol := db.protocols.get(protocol_id)) is None:
        raise exceptions.NotFoundException()
    
    if (kit := db.kits.get(kit_id)) is None:
        raise exceptions.NotFoundException()
    
    links = db.links.get_protocol_kit_links(protocol=protocol, kit=kit)
    
    for link in links:
        protocol.kit_links.remove(link)

    db.protocols.update(protocol)
    db.flush()

    sort_by = request.args.get("sort_by", "name")
    sort_order = request.args.get("sort_order", "asc")
    descending = sort_order == "desc"

    if sort_by not in models.Protocol.sortable_fields:
        raise exceptions.BadRequestException()
    
    kits, _ = db.kits.find(protocol=protocol, count_pages=False, limit=None, sort_by=sort_by, descending=descending)

    return make_response(
        render_template(
            "components/tables/protocol-kit.html",
            protocol=protocol, kits=kits,
            sort_by=sort_by, sort_order=sort_order,
        )
    )

@wrappers.htmx_route(protocols_htmx, db=db, methods=["DELETE"])
def remove_kit_combination(current_user: models.User, protocol_id: int, kit_id: int, combination_num: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (protocol := db.protocols.get(protocol_id)) is None:
        raise exceptions.NotFoundException()
    
    if (kit := db.kits.get(kit_id)) is None:
        raise exceptions.NotFoundException()
    
    links = db.links.get_protocol_kit_links(protocol=protocol, kit=kit)
    
    for link in links:
        if link.combination_num == combination_num:
            protocol.kit_links.remove(link)
        
    db.protocols.update(protocol)
    db.flush()

    sort_by = request.args.get("sort_by", "name")
    sort_order = request.args.get("sort_order", "asc")
    descending = sort_order == "desc"

    if sort_by not in models.Protocol.sortable_fields:
        raise exceptions.BadRequestException()
    
    kits, _ = db.kits.find(protocol=protocol, count_pages=False, limit=None, sort_by=sort_by, descending=descending)

    return make_response(
        render_template(
            "components/tables/protocol-kit.html",
            protocol=protocol, kits=kits,
            sort_by=sort_by, sort_order=sort_order,
        )
    )