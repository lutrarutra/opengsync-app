from flask import Blueprint, render_template, request, url_for, flash
from flask_htmx import make_response

from opengsync_db import models

from ... import db, forms, logic
from ...core import wrappers, exceptions


protocols_htmx = Blueprint("protocols_htmx", __name__, url_prefix="/htmx/protocols/")


@wrappers.htmx_route(protocols_htmx, db=db, cache_timeout_seconds=60, cache_type="global")
def get(current_user: models.User):
    context = logic.tables.render_protocol_table(current_user=current_user, request=request)
    return make_response(render_template(**context))


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
    flash("Kit Removed!", "success")
    return make_response(render_template(**logic.tables.render_kit_table(current_user=current_user, protocol=protocol, request=request)))

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
    flash("Kit Combination Removed!", "success")
    return make_response(render_template(**logic.tables.render_kit_table(current_user=current_user, protocol=protocol, request=request)))


@wrappers.htmx_route(protocols_htmx, db=db, methods=["DELETE"])
def delete(current_user: models.User, protocol_id: int):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if (protocol := db.protocols.get(protocol_id)) is None:
        raise exceptions.NotFoundException()
    
    db.protocols.delete(protocol)
    flash(f"Protocol '{protocol.name}' deleted.", "success")
    return make_response(redirect=url_for("protocols_page.protocols"))