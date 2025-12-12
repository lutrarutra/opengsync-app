import json

from flask import Blueprint, render_template, request, url_for, flash
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import AffiliationType, UserRole, ProjectStatus

from ... import db, forms
from ...core import wrappers, exceptions

groups_htmx = Blueprint("groups_htmx", __name__, url_prefix="/htmx/groups/")


@wrappers.htmx_route(groups_htmx, db=db)
def get(current_user: models.User, page: int = 0):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    groups: list[models.Group] = []

    if not current_user.is_insider():
        user_id = current_user.id
    else:
        user_id = None

    groups, n_pages = db.groups.find(
        user_id=user_id, sort_by=sort_by, descending=descending, offset=offset, count_pages=True
    )

    return make_response(
        render_template(
            "components/tables/group.html", groups=groups, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order,
            active_page=page
        )
    )


@wrappers.htmx_route(groups_htmx, db=db, methods=["POST"])
def query(current_user: models.User):
    if (field_name := next(iter(request.form.keys()))) is None:
        raise exceptions.BadRequestException()
    
    query = request.form[field_name]
    
    if (user_id := request.args.get("user_id")) is not None:
        try:
            user_id = int(user_id)
        except ValueError:
            raise exceptions.BadRequestException()
    else:
        user_id = current_user.id if not current_user.is_insider() else None
    
    groups = db.groups.query(name=query, user_id=user_id)
    return make_response(
        render_template(
            "components/search/group.html",
            results=groups, field_name=field_name,
        )
    )


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
def get_users(current_user: models.User, group_id: int, page: int = 0):
    sort_by = request.args.get("sort_by", "affiliation_type_id")
    sort_order = request.args.get("sort_order", "asc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if (group := db.groups.get(group_id)) is None:
        raise exceptions.NotFoundException()

    affiliations, n_pages = db.groups.get_affiliations(
        group_id=group_id, sort_by=sort_by, descending=descending, offset=offset, count_pages=True
    )

    affiliation = db.groups.get_user_affiliation(user_id=current_user.id, group_id=group_id)
    can_edit = current_user.role == UserRole.ADMIN or (affiliation is not None and affiliation.affiliation_type == AffiliationType.OWNER)
    can_add_users = current_user.is_insider() or (affiliation is not None and affiliation.affiliation_type in (AffiliationType.OWNER, AffiliationType.MANAGER))

    return make_response(
        render_template(
            "components/tables/group-user.html", affiliations=affiliations, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order, active_page=page, group=group,
            can_edit=can_edit, can_add_users=can_add_users, affiliation=affiliation
        )
    )


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
