from flask import Blueprint, render_template, request, url_for, flash
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import AffiliationType, UserRole, ProjectStatus

from ... import db, forms, logic
from ...core import wrappers, exceptions

groups_htmx = Blueprint("groups_htmx", __name__, url_prefix="/htmx/groups/")


@wrappers.htmx_route(groups_htmx, db=db)
def get(current_user: models.User):
    context = logic.group.get_table_context(current_user=current_user, request=request)
    return make_response(render_template(**context))


@wrappers.htmx_route(groups_htmx, db=db)
def search(current_user: models.User):
    context = logic.group.get_search_context(current_user=current_user, request=request)
    return make_response(render_template(**context))


@wrappers.htmx_route(groups_htmx, db=db, methods=["POST"])
def create(current_user: models.User):
    return forms.models.GroupForm(request.form).process_request(user=current_user)


@wrappers.htmx_route(groups_htmx, db=db, methods=["POST"])
def edit(current_user: models.User, group_id: int):
    if (group := db.groups.get(group_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider():
        if (affiliation := db.groups.get_user_affiliation(user_id=current_user.id, group_id=group_id)) is None:
            raise exceptions.NoPermissionsException()
        if affiliation.affiliation_type != AffiliationType.OWNER:
            raise exceptions.NoPermissionsException()

    return forms.models.GroupForm(request.form, group=group).process_request(user=current_user)


@wrappers.htmx_route(groups_htmx, db=db)
def get_affiliations(current_user: models.User, page: int = 0):
    context = logic.affiliation.get_table_context(current_user=current_user, request=request, page=page)
    return make_response(render_template(**context))


@wrappers.htmx_route(groups_htmx, db=db, methods=["DELETE"])
def remove_user(current_user: models.User, group_id: int):
    if (_ := db.groups.get(group_id)) is None:
        raise exceptions.NotFoundException()
    
    if (user_id := request.args.get("user_id")) is None:
        raise exceptions.BadRequestException()
    
    try:
        user_id = int(user_id)
    except ValueError:
        raise exceptions.BadRequestException()
    
    if not current_user.is_insider():
        if (affiliation := db.groups.get_user_affiliation(user_id=current_user.id, group_id=group_id)) is None:
            raise exceptions.NoPermissionsException()
        if affiliation.affiliation_type not in (AffiliationType.OWNER, AffiliationType.MANAGER):
            raise exceptions.NoPermissionsException()
    
    if (affiliation := db.groups.get_user_affiliation(user_id=user_id, group_id=group_id)) is None:
        raise exceptions.NotFoundException()
    
    if affiliation.affiliation_type == AffiliationType.OWNER:
        flash("Owner cannot be removed", "warning")
        return make_response(redirect=url_for("groups_page.group", group_id=group_id))
    
    db.groups.remove_user(user_id=user_id, group_id=group_id)
    flash("User removed from group", "success")
    return make_response(redirect=url_for("groups_page.group", group_id=group_id))


@wrappers.htmx_route(groups_htmx, db=db, methods=["POST"])
def make_owner(current_user: models.User, group_id: int):
    if (group := db.groups.get(group_id)) is None:
        raise exceptions.NotFoundException()
    
    if (user_id := request.args.get("user_id")) is None:
        raise exceptions.BadRequestException()
    
    try:
        user_id = int(user_id)
    except ValueError:
        raise exceptions.BadRequestException()
    
    if group.owner.id == user_id:
        raise exceptions.BadRequestException("User is already the owner")
    
    if not current_user.is_insider():
        if (affiliation := db.groups.get_user_affiliation(user_id=current_user.id, group_id=group_id)) is None:
            raise exceptions.NoPermissionsException()
        if affiliation.affiliation_type not in (AffiliationType.OWNER,):
            raise exceptions.NoPermissionsException()
    
    if (affiliation := db.groups.get_user_affiliation(user_id=user_id, group_id=group_id)) is None:
        raise exceptions.NoPermissionsException()
    
    db.groups.change_user_affiliation(user_id=group.owner.id, group_id=group_id, new_affiliation_type=AffiliationType.MANAGER)
    affiliation.affiliation_type = AffiliationType.OWNER
    db.session.add(affiliation)
    
    flash("Owner Changed!", "success")
    return make_response(redirect=url_for("groups_page.group", group_id=group_id))


@wrappers.htmx_route(groups_htmx, db=db, methods=["GET", "POST"])
def add_user(current_user: models.User, group_id: int):
    if (group := db.groups.get(group_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider():
        if (affiliation := db.groups.get_user_affiliation(user_id=current_user.id, group_id=group_id)) is None:
            raise exceptions.NoPermissionsException()
        if affiliation.affiliation_type not in (AffiliationType.OWNER, AffiliationType.MANAGER):
            raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        return forms.AddUserToGroupForm(group=group).make_response()
    
    if request.method == "POST":
        return forms.AddUserToGroupForm(group=group, formdata=request.form).process_request()
    
    else:
        raise exceptions.BadRequestException()
