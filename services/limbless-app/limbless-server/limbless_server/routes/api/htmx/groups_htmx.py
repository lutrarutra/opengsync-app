from typing import TYPE_CHECKING
import json

from flask import Blueprint, render_template, abort, request, url_for, flash
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, db_session, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, AffiliationType, UserRole, ProjectStatus
from .... import db, forms

if TYPE_CHECKING:
    current_user: models.User = None   # type: ignore
else:
    from flask_login import current_user

groups_htmx = Blueprint("groups_htmx", __name__, url_prefix="/api/hmtx/groups/")


@groups_htmx.route("get/<int:page>", methods=["GET"])
@groups_htmx.route("get", methods=["GET"], defaults={"page": 0})
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    groups: list[models.Group] = []

    if not current_user.is_insider():
        user_id = current_user.id
    else:
        user_id = None

    groups, n_pages = db.get_groups(
        user_id=user_id, sort_by=sort_by, descending=descending, offset=offset, count_pages=True
    )

    return make_response(
        render_template(
            "components/tables/group.html", groups=groups, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order,
            active_page=page
        )
    )


@groups_htmx.route("query", methods=["POST"])
@db_session(db)
@login_required
def query():
    if (field_name := next(iter(request.form.keys()))) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    query = request.form[field_name]
    
    if (user_id := request.args.get("user_id")) is not None:
        try:
            user_id = int(user_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    else:
        user_id = current_user.id if not current_user.is_insider() else None
    
    groups = db.query_groups(name=query, user_id=user_id)
    return make_response(
        render_template(
            "components/search_select_results.html",
            results=groups, field_name=field_name,
        )
    )


@groups_htmx.route("create", methods=["POST"])
@login_required
def create():
    return forms.models.GroupForm(request.form).process_request(user=current_user)


@groups_htmx.route("<int:group_id>/edit", methods=["POST"])
@db_session(db)
@login_required
def edit(group_id: int):
    if (group := db.get_group(group_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider():
        if (affiliation := db.get_group_user_affiliation(user_id=current_user.id, group_id=group_id)) is None:
            return abort(HTTPResponse.FORBIDDEN.id)
        if affiliation.affiliation_type != AffiliationType.OWNER:
            return abort(HTTPResponse.FORBIDDEN.id)

    return forms.models.GroupForm(request.form, group=group).process_request(user=current_user)


@groups_htmx.route("<int:group_id>/get_users/<int:page>", methods=["GET"])
@groups_htmx.route("<int:group_id>/get_users", methods=["GET"], defaults={"page": 0})
@db_session(db)
@login_required
def get_users(group_id: int, page: int):
    sort_by = request.args.get("sort_by", "affiliation_type_id")
    sort_order = request.args.get("sort_order", "asc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if (group := db.get_group(group_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    affiliations, n_pages = db.get_group_affiliations(
        group_id=group_id, sort_by=sort_by, descending=descending, offset=offset, count_pages=True
    )

    affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=group_id)
    can_edit = current_user.role == UserRole.ADMIN or (affiliation is not None and affiliation.affiliation_type == AffiliationType.OWNER)
    can_add_users = current_user.is_insider() or (affiliation is not None and affiliation.affiliation_type in (AffiliationType.OWNER, AffiliationType.MANAGER))

    return make_response(
        render_template(
            "components/tables/group-user.html", affiliations=affiliations, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order, active_page=page, group=group,
            can_edit=can_edit, can_add_users=can_add_users, affiliation=affiliation
        )
    )


@groups_htmx.route("<int:group_id>/remove_user", methods=["DELETE"])
@db_session(db)
@login_required
def remove_user(group_id: int):
    if (_ := db.get_group(group_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if (user_id := request.args.get("user_id")) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    try:
        user_id = int(user_id)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if not current_user.is_insider():
        if (affiliation := db.get_group_user_affiliation(user_id=current_user.id, group_id=group_id)) is None:
            return abort(HTTPResponse.FORBIDDEN.id)
        if affiliation.affiliation_type not in (AffiliationType.OWNER, AffiliationType.MANAGER):
            return abort(HTTPResponse.FORBIDDEN.id)
    
    if (affiliation := db.get_group_user_affiliation(user_id=user_id, group_id=group_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if affiliation.affiliation_type == AffiliationType.OWNER:
        flash("Owner cannot be removed", "warning")
        return make_response(redirect=url_for("groups_page.group_page", group_id=group_id))
    
    db.remove_user_from_group(user_id=user_id, group_id=group_id)
    flash("User removed from group", "success")
    return make_response(redirect=url_for("groups_page.group_page", group_id=group_id))


@groups_htmx.route("<int:group_id>/add_user", methods=["GET", "POST"])
@db_session(db)
@login_required
def add_user(group_id: int):
    if (group := db.get_group(group_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider():
        if (affiliation := db.get_group_user_affiliation(user_id=current_user.id, group_id=group_id)) is None:
            return abort(HTTPResponse.FORBIDDEN.id)
        if affiliation.affiliation_type not in (AffiliationType.OWNER, AffiliationType.MANAGER):
            return abort(HTTPResponse.FORBIDDEN.id)
    
    if request.method == "GET":
        return forms.AddUserToGroupForm(group=group).make_response()
    
    if request.method == "POST":
        return forms.AddUserToGroupForm(group=group, formdata=request.form).process_request()
    
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)


@groups_htmx.route("<int:group_id>/get_seq_requests/<int:page>", methods=["GET"])
@groups_htmx.route("<int:group_id>/get_seq_requests", methods=["GET"], defaults={"page": 0})
@db_session(db)
@login_required
def get_seq_requests(group_id: int, page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if (group := db.get_group(group_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    seq_requests, n_pages = db.get_seq_requests(
        group_id=group_id, sort_by=sort_by, descending=descending, offset=offset, count_pages=True
    )

    return make_response(
        render_template(
            "components/tables/group-seq_request.html", seq_requests=seq_requests, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order, active_page=page, group=group
        )
    )


@groups_htmx.route("<int:group_id>/get_projects/<int:page>", methods=["GET"])
@groups_htmx.route("<int:group_id>/get_projects", methods=["GET"], defaults={"page": 0})
@db_session(db)
@login_required
def get_projects(group_id: int, page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if (group := db.get_group(group_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [ProjectStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    projects, n_pages = db.get_projects(
        group_id=group_id, sort_by=sort_by, descending=descending, offset=offset, count_pages=True,
        status_in=status_in
    )

    return make_response(
        render_template(
            "components/tables/group-project.html", projects=projects, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order, active_page=page, group=group,
            status_in=status_in
        )
    )