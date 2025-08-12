from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import HTTPResponse, UserRole
from .... import db, logger, forms
from ....core import wrappers

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

share_tokens_htmx = Blueprint("share_tokens_htmx", __name__, url_prefix="/api/hmtx/share_tokens/")


@wrappers.htmx_route(share_tokens_htmx, db=db)
def get(page: int = 0):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "created_utc")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page
    
    share_tokens: list[models.ShareToken] = []

    share_tokens, n_pages = db.get_share_tokens(
        offset=offset, sort_by=sort_by, descending=descending, count_pages=True
    )
    
    return make_response(
        render_template(
            "components/tables/share_token.html", share_tokens=share_tokens,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
        )
    )
