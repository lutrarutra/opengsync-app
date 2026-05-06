import json

from flask import Blueprint, render_template, request, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import KitType

from ... import db, forms, logger, logic
from ...core import wrappers, exceptions


kits_htmx = Blueprint("kits_htmx", __name__, url_prefix="/htmx/kits/")


@wrappers.htmx_route(kits_htmx, db=db, cache_timeout_seconds=60, cache_type="global")
def get(current_user: models.User):
    context = logic.kit.get_table_context(current_user=current_user, request=request)
    return make_response(render_template(**context))


@wrappers.htmx_route(kits_htmx, db=db, methods=["GET", "POST"])
def create(current_user: models.User):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        return forms.models.KitForm(form_type="create").make_response()
    elif request.method == "POST":
        form = forms.models.KitForm(form_type="create", formdata=request.form)
        return form.process_request()
    else:
        raise exceptions.MethodNotAllowedException()


@wrappers.htmx_route(kits_htmx, db=db, methods=["GET", "POST"])
def edit(current_user: models.User, kit_id: int):
    if not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    if (kit := db.kits.get(kit_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        return forms.models.KitForm(form_type="edit", kit=kit).make_response()
    elif request.method == "POST":
        form = forms.models.KitForm(form_type="edit", formdata=request.form, kit=kit)
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