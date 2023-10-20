from typing import Literal

from flask import Blueprint, url_for, render_template, flash, request, abort, redirect
from flask_htmx import make_response
from flask_login import current_user, login_required

from .... import db, forms, logger, models
from ....core import DBSession
from ....categories import HttpResponse

users_htmx = Blueprint("users_htmx", __name__, url_prefix="/api/users/")


@users_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by")
    order = request.args.get("order", "inc")
    reversed = order == "desc"

    if sort_by not in models.User.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    with DBSession(db.db_handler) as session:
        n_pages = int(session.get_num_users() / 20)
        page = min(page, n_pages)
        users = session.get_users(limit=20, offset=page * 20, sort_by=sort_by, reversed=reversed)
        
        return make_response(
            render_template(
                "components/tables/user.html", users=users,
                page=page, n_pages=n_pages,
                current_sort=sort_by, current_sort_order=order
            ), push_url=False
        )


@users_htmx.route("email/<int:user_id>", methods=["GET"])
@login_required
def email(user_id: int):
    if (user := models.User.get(user_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    return make_response(
        redirect="mailto:" + user.email
    )