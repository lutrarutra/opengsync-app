import json

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import HTTPResponse, RunStatus
from .... import db, logger, cache  # noqa F401
from ....core import wrappers

seq_runs_htmx = Blueprint("seq_runs_htmx", __name__, url_prefix="/api/hmtx/seq_run/")


@wrappers.htmx_route(seq_runs_htmx, db=db)
@cache.cached(timeout=60, query_string=True)
def get(current_user: models.User, page: int = 0):
    sort_by = request.args.get("sort_by", "run_folder")
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

    seq_runs, n_pages = db.get_seq_runs(offset=offset, sort_by=sort_by, descending=descending, status_in=status_in, count_pages=True)
    
    return make_response(render_template(
        "components/tables/seq_run.html", seq_runs=seq_runs, n_pages=n_pages,
        active_page=page, sort_by=sort_by, sort_order=sort_order, status_in=status_in,
    ))


@wrappers.htmx_route(seq_runs_htmx, db=db)
def table_query(current_user: models.User):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (word := request.args.get("experiment_name", None)) is not None:
        field_name = "experiment_name"
    elif (word := request.args.get("id", None)) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    seq_runs = []
    if field_name == "experiment_name":
        seq_runs = db.query_seq_runs(word)

    elif field_name == "id":
        try:
            if (seq_run := db.get_seq_run(int(word))) is not None:
                seq_runs.append(seq_run)
        except ValueError:
            pass
        
    return make_response(render_template("components/tables/seq_run.html", seq_runs=seq_runs, current_query=word, field_name=field_name))