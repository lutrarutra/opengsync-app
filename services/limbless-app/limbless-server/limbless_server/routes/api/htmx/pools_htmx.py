from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT
from limbless_db.categories import HTTPResponse

from .... import db, forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

pools_htmx = Blueprint("pools_htmx", __name__, url_prefix="/api/hmtx/pools/")


@pools_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page

    pools: list[models.Pool] = []
    context = {}
    
    with DBSession(db) as session:
        if (experiment_id := request.args.get("experiment_id")) is not None:
            template = "components/tables/experiment-pool.html"
            try:
                experiment_id = int(experiment_id)
            except ValueError:
                return abort(HTTPResponse.BAD_REQUEST.id)
            
            if (experiment := session.get_experiment(experiment_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            
            pools, n_pages = session.get_pools(
                experiment_id=experiment_id, sort_by=sort_by, descending=descending,
                offset=offset,
            )
            context["experiment"] = experiment
            context["experiment_lanes"] = session.get_lanes_in_experiment(experiment_id)

        elif "select" in request.args.keys():
            template = "components/tables/select-pool.html"
            pools, n_pages = session.get_pools(
                sort_by=sort_by, descending=descending,
                offset=offset,
            )
        else:
            template = "components/tables/pool.html"
            pools, n_pages = session.get_pools(
                sort_by=sort_by, descending=descending,
                offset=offset,
            )

        return make_response(
            render_template(
                template, pools=pools, pools_n_pages=n_pages,
                pools_current_sort=sort_by, pools_current_sort_order=order,
                pools_active_page=page, **context
            )
        )
    

@pools_htmx.route("<int:pool_id>/edit", methods=["POST"])
@login_required
def edit(pool_id: int):
    with DBSession(db) as session:
        if (pool := session.get_pool(pool_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if not current_user.is_insider() and pool.owner_id != current_user.id:
            return abort(HTTPResponse.FORBIDDEN.id)
        
        return forms.models.PoolForm(None, request.form).process_request(pool=pool)


@pools_htmx.route("table_query", methods=["POST"])
@login_required
def table_query():
    raise NotImplementedError()
