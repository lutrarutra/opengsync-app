from flask import Blueprint, render_template, request, Request
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT, queries as Q

from ... import db, forms, logger
from ...core import exceptions
from ...core import wrappers

api_tokens_htmx = Blueprint("api_tokens_htmx", __name__, url_prefix="/htmx/api_tokens/")


@wrappers.htmx_route(api_tokens_htmx, db=db, methods=["GET", "POST"])
def create(current_user: models.User, user_id: int):
    if (user := db.session.first(Q.user.select(id=user_id))) is None:
        raise exceptions.NotFoundException(f"User with ID '{user_id}' not found.")
    
    if not current_user.is_admin and current_user.id != user.id:
        raise exceptions.NoPermissionsException("You do not have permission to create API tokens for this user.")

    if not user.is_insider:
        raise exceptions.NoPermissionsException("API tokens can only be created for insider users.")
    
    form = forms.models.APITokenForm(user=user, formdata=request.form if request.method == "POST" else None)
    if request.method == "GET":
        return form.make_response()
    
    return form.process_request()

@wrappers.htmx_route(api_tokens_htmx, db=db, methods=["POST"])
def deactivate(current_user: models.User, token_id: int):
    if (token := db.session.first(Q.api_token.select(id=token_id))) is None:
        raise exceptions.NotFoundException(f"API Token with ID '{token_id}' not found.")
    
    if token.owner_id != current_user.id and not current_user.is_admin:
        raise exceptions.NoPermissionsException("You do not have permission to inactivate this API token.")
    
    token._expired = True
    db.session.save(token)

    page = int(request.args.get("page", "0"))
    
    sort_by = request.args.get("sort_by", "created_utc")
    descending = request.args.get("sort_order", "desc") == "desc"

    try:
        order_by = getattr(getattr(models.APIToken, sort_by), "desc" if descending else "asc")()
    except AttributeError:
        raise exceptions.BadRequestException()

    if (user_id := request.args.get("user_id")) is not None:
        if (owner := db.session.first(Q.user.select(id=int(user_id)))) is None:
            raise exceptions.NotFoundException(f"User with ID '{user_id}' not found.")
    else:
        owner = None
    
    query = Q.api_token.select(
        owner=owner,
    ).order_by(order_by)
    tokens, count = db.session.page(
        statement=query, page=page, limit=PAGE_LIMIT
    )
    n_pages = (count + PAGE_LIMIT - 1) // PAGE_LIMIT

    return make_response(
        render_template(
            "components/tables/user-api_token.html", tokens=tokens, n_pages=n_pages, user=owner
        )
    )
