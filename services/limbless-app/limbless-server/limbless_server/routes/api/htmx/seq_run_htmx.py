from typing import Optional, TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, request, abort, Response
from flask_htmx import make_response
from flask_login import login_required
from werkzeug.utils import secure_filename

import pandas as pd

from limbless_db import models, DBSession, PAGE_LIMIT, DBHandler
from limbless_db.categories import HTTPResponse, UserRole
from .... import db, logger, forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

seq_run_htmx = Blueprint("seq_run_htmx", __name__, url_prefix="/api/hmtx/seq_run/")


@seq_run_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    if not (sort_by := request.args.get("sort_by", None)):
        sort_by = "id"
    
    if not (order := request.args.get("order", None)):
        order = "desc"

    descending = order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.SeqRun.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    seq_runs: list[models.SeqRun] = []

    with DBSession(db) as session:
        seq_runs, n_pages = session.get_seq_runs(offset=offset, sort_by=sort_by, descending=descending)
    
    return make_response(render_template("components/tables/seq_run.html", seq_runs=seq_runs, n_pages=n_pages, page=page, sort_by=sort_by, order=order))