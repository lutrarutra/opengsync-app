from typing import Literal

from flask import Blueprint, url_for, render_template, flash, request, abort, redirect
from flask_htmx import make_response
from flask_login import current_user, login_required

from .... import db, forms, logger, models
from ....core import DBSession
from ....categories import HttpResponse, UserRole

users_htmx = Blueprint("users_htmx", __name__, url_prefix="/api/users/")


@users_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
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

@users_htmx.route("table_query", methods=["POST"])
@login_required
def table_query():
    if current_user.role_type not in [UserRole.ADMIN, UserRole.BIOINFORMATICIAN, UserRole.TECHNICIAN]:
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (word := request.form.get("first_name", None)) is not None:
        field_name = "first_name"
    elif (word := request.form.get("last_name", None)) is not None:
        field_name = "last_name"
    elif (word := request.form.get("email", None)) is not None:
        field_name = "email"
    else:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    if word is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    if field_name == "first_name" or field_name == "last_name":
        users = db.db_handler.query_users(word)
    elif field_name == "email":
        users = db.db_handler.query_users_by_email(word)
    else:
        assert False  # This should never happen

    return make_response(
        render_template(
            "components/tables/user.html",
            current_query=word,
            users=users,
            field_name=field_name
        ), push_url=False
    )
