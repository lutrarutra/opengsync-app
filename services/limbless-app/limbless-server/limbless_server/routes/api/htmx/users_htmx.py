from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT
from limbless_db.core.categories import HttpResponse, UserRole
from .... import db, logger

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

users_htmx = Blueprint("users_htmx", __name__, url_prefix="/api/users/")


@users_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"

    if sort_by not in models.User.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.id)

    with DBSession(db) as session:
        users, n_pages = session.get_users(offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending)
        
        return make_response(
            render_template(
                "components/tables/user.html", users=users,
                users_active_page=page, users_n_pages=n_pages,
                users_current_sort=sort_by, users_current_sort_order=order
            ), push_url=False
        )


@users_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.form.keys()))
    query = request.form.get(field_name)

    if query is None:
        return abort(HttpResponse.BAD_REQUEST.id)
    
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
    
    results = db.query_users(query, with_roles=with_roles, only_insiders=only_insiders)
    
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
        return abort(HttpResponse.FORBIDDEN.id)
    
    if (word := request.form.get("first_name", None)) is not None:
        field_name = "first_name"
    elif (word := request.form.get("last_name", None)) is not None:
        field_name = "last_name"
    elif (word := request.form.get("email", None)) is not None:
        field_name = "email"
    elif (word := request.form.get("id", None)) is not None:
        field_name = "id"
    else:
        return abort(HttpResponse.BAD_REQUEST.id)

    if word is None:
        return abort(HttpResponse.BAD_REQUEST.id)

    if field_name == "first_name" or field_name == "last_name":
        users = db.query_users(word)
    elif field_name == "email":
        users = db.query_users_by_email(word)
    elif field_name == "id":
        try:
            user_id = int(word)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.id)
        else:
            users = [db.get_user(user_id)]
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
