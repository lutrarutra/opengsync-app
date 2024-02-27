from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT
from limbless_db.core.categories import HttpResponse
from .... import db

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

pools_htmx = Blueprint("pools_htmx", __name__, url_prefix="/api/pools/")


@pools_htmx.route("get", methods=["GET"])
@login_required
def get(page):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.id)
    
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
            return abort(HttpResponse.BAD_REQUEST.id)
        
        with DBSession(db) as session:
            if (experiment := session.get_experiment(experiment_id)) is None:
                return abort(HttpResponse.NOT_FOUND.id)
            
            pools, n_pages = session.get_pools(
                experiment_id=experiment_id, sort_by=sort_by, descending=descending,
                offset=offset, 
            )
            context["experiment"] = experiment

    else:
        template = "components/tables/pool.html"
        with DBSession(db) as session:
            pools, n_pages = session.get_pools(
                sort_by=sort_by, descending=descending,
                offset=offset, 
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
    raise NotImplementedError()
