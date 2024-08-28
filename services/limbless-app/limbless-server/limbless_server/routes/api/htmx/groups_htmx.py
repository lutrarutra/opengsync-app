from typing import TYPE_CHECKING

from flask import Blueprint, render_template, abort, request
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, db_session, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, AffiliationType
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
        user_id=user_id, sort_by=sort_by, descending=descending, offset=offset
    )

    return make_response(
        render_template(
            "components/tables/group.html", groups=groups, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order,
            active_page=page
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
        group_id=group_id, sort_by=sort_by, descending=descending, offset=offset
    )

    return make_response(
        render_template(
            "components/tables/group-user.html", affiliations=affiliations, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order, active_page=page, group=group
        )
    )