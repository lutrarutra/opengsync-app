import json
from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, RunStatus
from .... import db, logger, forms  # noqa F401

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

seq_runs_htmx = Blueprint("seq_runs_htmx", __name__, url_prefix="/api/hmtx/seq_run/")


@seq_runs_htmx.route("get", methods=["GET"], defaults={"page": 0})
@seq_runs_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [RunStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    seq_runs, n_pages = db.get_seq_runs(offset=offset, sort_by=sort_by, descending=descending, status_in=status_in)
    
    return make_response(render_template(
        "components/tables/seq_run.html", seq_runs=seq_runs, n_pages=n_pages,
        active_page=page, sort_by=sort_by, sort_order=sort_order, status_in=status_in, 
    ))