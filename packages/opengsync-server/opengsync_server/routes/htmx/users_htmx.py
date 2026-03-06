from flask import Blueprint, render_template, request
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT

from ... import db, logger, forms, logic
from ...core import wrappers, exceptions

users_htmx = Blueprint("users_htmx", __name__, url_prefix="/htmx/users/")


@wrappers.htmx_route(users_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get(current_user: models.User):
    context = logic.user.get_table_context(current_user=current_user, request=request)
    return make_response(render_template(**context))

@wrappers.htmx_route(users_htmx, db=db)
def search(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    return make_response(render_template(**logic.user.get_search_context(current_user=current_user, request=request)))

@wrappers.htmx_route(users_htmx, db=db)
def get_affiliations(current_user: models.User):
    context = logic.affiliation.get_table_context(current_user=current_user, request=request)
    return make_response(render_template(**context))

@wrappers.htmx_route(users_htmx, db=db)
def get_api_tokens(current_user: models.User, user_id: int):
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    context = logic.tokens.get_table_context(current_user=current_user, request=request, user=user)
    return make_response(render_template(**context))

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