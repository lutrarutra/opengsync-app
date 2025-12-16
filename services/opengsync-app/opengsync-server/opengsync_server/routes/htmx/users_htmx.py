import json

from flask import Blueprint, render_template, request
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import UserRole, SeqRequestStatus, ProjectStatus

from ... import db, logger, forms, logic  # noqa F401
from ...core import wrappers, exceptions

users_htmx = Blueprint("users_htmx", __name__, url_prefix="/htmx/users/")


@wrappers.htmx_route(users_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get(current_user: models.User):
    context = logic.tables.render_user_table(current_user=current_user, request=request)
    return make_response(render_template(**context))

@wrappers.htmx_route(users_htmx, db=db, methods=["POST"])
def query(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    field_name = next(iter(request.form.keys()))
    query = request.form.get(field_name)

    if query is None:
        raise exceptions.BadRequestException()
    
    if (role_in := request.args.get("role_id_in")) is not None:
        role_in = json.loads(role_in)
        try:
            role_in = [UserRole.get(int(role)) for role in role_in]
        except ValueError:
            raise exceptions.BadRequestException()
        
        if len(role_in) == 0:
            role_in = None

    only_insiders = request.args.get("only_insiders") == "True"
    results = db.users.query(query, role_in=role_in, only_insiders=only_insiders)
    
    return make_response(
        render_template(
            "components/search/user.html",
            results=results, field_name=field_name
        )
    )


@wrappers.htmx_route(users_htmx, db=db)
def table_query(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (word := request.args.get("last_name")) is not None:
        field_name = "last_name"
    elif (word := request.args.get("email")) is not None:
        field_name = "email"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        raise exceptions.BadRequestException()

    if (role_in := request.args.get("role_id_in")) is not None:
        role_in = json.loads(role_in)
        try:
            role_in = [UserRole.get(int(role)) for role in role_in]
        except ValueError:
            raise exceptions.BadRequestException()
        
        if len(role_in) == 0:
            role_in = None

    users: list[models.User] = []
    if field_name == "last_name":
        users = db.users.query(word, role_in=role_in)
    elif field_name == "email":
        users = db.users.query_with_email(word, role_in=role_in)
    elif field_name == "id":
        try:
            _id = int(word)
            if (user := db.users.get(_id)) is not None:
                users.append(user)
        except ValueError:
            pass

    return make_response(
        render_template(
            "components/tables/user.html",
            current_query=word, active_query_field=field_name,
            users=users, role_in=role_in
        )
    )


@wrappers.htmx_route(users_htmx, db=db)
def get_affiliations(current_user: models.User):
    context = logic.tables.render_affiliation_table(current_user=current_user, request=request)
    return make_response(render_template(**context))

@wrappers.htmx_route(users_htmx, db=db)
def get_api_tokens(current_user: models.User, user_id: int, page: int = 0):
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if user.id != current_user.id and not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "created_utc")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    tokens, n_pages = db.api_tokens.find(
        offset=offset, owner=user, sort_by=sort_by, descending=descending, count_pages=True
    )
    
    return make_response(
        render_template(
            "components/tables/user-api_token.html",
            user=user, tokens=tokens,
            active_page=page, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order
        )
    )

@wrappers.htmx_route(users_htmx, db=db, methods=["GET", "POST"])
def edit(current_user: models.User, user_id: int):
    if current_user.id != user_id and not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        return forms.models.UserForm(user=user, current_user=current_user).make_response()
    else:
        return forms.models.UserForm(user=user, current_user=current_user, formdata=request.form).process_request()