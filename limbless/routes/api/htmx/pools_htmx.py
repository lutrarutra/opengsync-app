from typing import Optional, TYPE_CHECKING
from io import StringIO

import pandas as pd
from flask import Blueprint, redirect, url_for, render_template, flash, request, abort
from flask_htmx import make_response
from flask_login import login_required

from .... import db, logger, forms, models, tools, PAGE_LIMIT
from ....core import DBSession, exceptions
from ....core.DBHandler import DBHandler
from ....categories import UserRole, HttpResponse, LibraryType

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user

pools_htmx = Blueprint("pools_htmx", __name__, url_prefix="/api/pools/")


@pools_htmx.route("get", methods=["POST"])
@login_required
def get(page):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page

    pools: list[models.Pool] = []
    context = {}
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        template = "components/tables/experiment-pool.html"
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        with DBSession(db.db_handler) as session:
            if (experiment := session.get_experiment(experiment_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
            access = session.get_user_experiment_access(current_user.id, experiment_id)
            if access is None:
                return abort(HttpResponse.FORBIDDEN.value.id)
            
            pools, n_pages = session.get_pools(
                experiment_id=experiment_id, sort_by=sort_by, descending=descending,
                offset=offset, limit=PAGE_LIMIT
            )
            context["experiment"] = experiment

    else:
        template = "components/tables/pool.html"
        with DBSession(db.db_handler) as session:
            pools, n_pages = session.get_pools(
                sort_by=sort_by, descending=descending,
                offset=offset, limit=PAGE_LIMIT
            )

    return make_response(
        render_template(
            template, pools=pools, pools_n_pages=n_pages,
            pools_active_page=page, **context
        )
    )


@pools_htmx.route("table_query", methods=["POST"])
@login_required
def table_query():
    abort(404)
