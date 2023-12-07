from typing import Literal, TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, request, abort, redirect
from flask_htmx import make_response
from flask_login import current_user, login_required

from .... import db, forms, logger, models, PAGE_LIMIT
from ....core import DBSession
from ....categories import HttpResponse, UserRole

users_htmx = Blueprint("users_htmx", __name__, url_prefix="/api/users/")


@users_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"

    if sort_by not in models.User.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    with DBSession(db.db_handler) as session:
        users, n_pages = session.get_users(limit=PAGE_LIMIT, offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending)
        
        return make_response(
            render_template(
                "components/tables/user.html", users=users,
                users_active_page=page, users_n_pages=n_pages,
                current_sort=sort_by, current_sort_order=order
            ), push_url=False
        )


@users_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.form.keys()))
    query = request.form.get(field_name)

    if query is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if (raw_roles := request.args.get("roles", None)) is not None:
        logger.debug(raw_roles)
        raw_roles = raw_roles.split(",")
        with_roles = []
        for raw_role in raw_roles:
            try:
                role_id = int(raw_role)
            except ValueError:
                continue
            with_roles.append(UserRole.get(role_id))
    else:
        with_roles = None

    only_insiders = request.args.get("only_insiders", None) == "True"
    
    results = db.db_handler.query_users(query, with_roles=with_roles, only_insiders=only_insiders)
    
    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results, field_name=field_name
        ), push_url=False
    )


@users_htmx.route("table_query", methods=["POST"])
@login_required
def table_query():
    if not current_user.is_insider():
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
