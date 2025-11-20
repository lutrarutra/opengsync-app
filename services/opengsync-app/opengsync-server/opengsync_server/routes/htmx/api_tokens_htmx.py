from flask import Blueprint, render_template, request, Request
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT

from ... import db, forms, logger
from ...core import exceptions
from ...core import wrappers

api_tokens_htmx = Blueprint("api_tokens_htmx", __name__, url_prefix="/htmx/api_tokens/")


def get_context(request: Request) -> dict:
    context = {}

    if (user_id := request.args.get("user_id")) is not None:
        if (user := db.users.get(int(user_id))) is None:
            raise exceptions.NotFoundException(f"User with ID '{user_id}' not found.")
        context["user"] = user

    page = int(request.args.get("page", "0"))
    
    context["sort_by"] = request.args.get("sort_by", "created_utc")
    context["sort_order"] = request.args.get("sort_order", "desc")
    context["descending"] = context["sort_order"] == "desc"
    context["offset"] = page * PAGE_LIMIT

    return context


@wrappers.htmx_route(api_tokens_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get(current_user: models.User, page: int = 0):
    raise NotImplementedError()
    context = get_context(request)

    api_tokens, n_pages = db.shares.find(
        offset=context["offset"], sort_by=context["sort_by"], descending=context["descending"], count_pages=True,
        owner=current_user if not current_user.is_insider() else None
    )

    return make_response(
        render_template(
            "components/tables/share_token.html", api_tokens=api_tokens,
            n_pages=n_pages, active_page=page,
            sort_by=context["sort_by"], sort_order=context["sort_order"],
        )
    )

@wrappers.htmx_route(api_tokens_htmx, db=db, methods=["GET", "POST"])
def create(current_user: models.User, user_id: int):
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException(f"User with ID '{user_id}' not found.")
    
    if not current_user.is_admin() and current_user.id != user.id:
        raise exceptions.NoPermissionsException("You do not have permission to create API tokens for this user.")

    if not user.is_insider():
        raise exceptions.NoPermissionsException("API tokens can only be created for insider users.")
    
    form = forms.models.APITokenForm(user=user, formdata=request.form if request.method == "POST" else None)
    if request.method == "GET":
        return form.make_response()
    
    return form.process_request()

@wrappers.htmx_route(api_tokens_htmx, db=db, methods=["POST"])
def deactivate(current_user: models.User, token_id: int):
    if (token := db.api_tokens.get(token_id)) is None:
        raise exceptions.NotFoundException(f"API Token with ID '{token_id}' not found.")
    
    if token.owner_id != current_user.id and not current_user.is_admin():
        raise exceptions.NoPermissionsException("You do not have permission to inactivate this API token.")
    
    token._expired = True
    db.api_tokens.update(token)

    context = get_context(request)

    tokens, n_pages = db.api_tokens.find(
        offset=context["offset"],
        sort_by=context["sort_by"],
        owner=context.get("user"),
        descending=context["descending"],
        count_pages=True
    )
    
    return make_response(
        render_template(
            "components/tables/user-api_token.html", tokens=tokens, n_pages=n_pages, **context
        )
    )
