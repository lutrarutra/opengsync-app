from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import HTTPResponse

from .... import db, forms, logger  # noqa
from ....core import wrappers

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

lanes_htmx = Blueprint("lanes_htmx", __name__, url_prefix="/api/hmtx/lanes/")


@wrappers.htmx_route(lanes_htmx, db=db)
def browse(workflow: str, page: int = 0):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    context = {}
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            context["experiment_id"] = experiment_id
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page
    
    lanes, n_pages = db.get_lanes(
        sort_by=sort_by, descending=descending, offset=offset, experiment_id=experiment_id, count_pages=True
    )

    context["workflow"] = workflow
    return make_response(
        render_template(
            "components/tables/select-lanes.html",
            lanes=lanes, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, context=context,
            workflow=workflow
        )
    )