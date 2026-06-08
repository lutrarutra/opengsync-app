from flask import Blueprint, render_template, request, url_for, flash
from flask_htmx import make_response
from sqlalchemy import orm
import sqlalchemy as sa

from opengsync_db import models, queries as Q

from ... import db, forms, logic
from ...core import wrappers, exceptions


protocols_htmx = Blueprint("protocols_htmx", __name__, url_prefix="/htmx/protocols/")


@wrappers.htmx_route(protocols_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get(current_user: models.User):
    context = logic.protocol.get_table_context(current_user=current_user, request=request)
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
    
    if (protocol := db.session.first(Q.protocol.select(id=protocol_id))) is None:
        raise exceptions.NotFoundException()

    form = forms.models.ProtocolForm(form_type="edit", formdata=request.form, protocol=protocol)

    if request.method == "POST":
        return form.process_request()
    return form.make_response()

@wrappers.htmx_route(protocols_htmx, db=db, methods=["DELETE"])
def remove_kit(current_user: models.User, protocol_id: int, kit_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (protocol := db.session.first(Q.protocol.select(id=protocol_id), options=[
        orm.selectinload(models.Protocol.kit_links)
    ])) is None:
        raise exceptions.NotFoundException()
    
    if (links := db.session.get_all(sa.select(models.links.ProtocolKitLink).where(
        models.links.ProtocolKitLink.protocol_id == protocol_id,
        models.links.ProtocolKitLink.kit_id == kit_id
    ), limit=None)) is None:
        raise exceptions.NotFoundException()
    
    for link in links:
        protocol.kit_links.remove(link)

    flash("Kit Removed!", "success")
    return make_response(render_template(**logic.kit.get_table_context(current_user=current_user, protocol=protocol, request=request)))

@wrappers.htmx_route(protocols_htmx, db=db, methods=["DELETE"])
def remove_kit_combination(current_user: models.User, protocol_id: int, kit_id: int, combination_num: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (protocol := db.session.first(Q.protocol.select(id=protocol_id))) is None:
        raise exceptions.NotFoundException()
    
    if (kit_link := db.session.first(sa.select(models.links.ProtocolKitLink).where(
        models.links.ProtocolKitLink.protocol_id == protocol_id,
        models.links.ProtocolKitLink.kit_id == kit_id,
        models.links.ProtocolKitLink.combination_num == combination_num
    ))) is None:
        raise exceptions.NotFoundException()
    
    protocol.kit_links.remove(kit_link)
        
    flash("Kit Combination Removed!", "success")
    return make_response(render_template(**logic.kit.get_table_context(current_user=current_user, protocol=protocol, request=request)))


@wrappers.htmx_route(protocols_htmx, db=db, methods=["DELETE"])
def delete(current_user: models.User, protocol_id: int):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if (protocol := db.session.first(Q.protocol.select(id=protocol_id))) is None:
        raise exceptions.NotFoundException()
    
    db.session.delete(protocol)
    flash(f"Protocol '{protocol.name}' deleted.", "success")
    return make_response(redirect=url_for("protocols_page.protocols"))