from flask import Blueprint, render_template, request
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT

from ... import db
from ...core import wrappers, exceptions

share_tokens_htmx = Blueprint("share_tokens_htmx", __name__, url_prefix="/htmx/share_tokens/")


@wrappers.htmx_route(share_tokens_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get(current_user: models.User, page: int = 0):
    sort_by = request.args.get("sort_by", "created_utc")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page
    
    share_tokens: list[models.ShareToken] = []

    share_tokens, n_pages = db.shares.find(
        offset=offset, sort_by=sort_by, descending=descending, count_pages=True,
        owner=current_user if not current_user.is_insider() else None
    )
    
    return make_response(
        render_template(
            "components/tables/share_token.html", share_tokens=share_tokens,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
        )
    )
