import json
from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, render_template
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession
from limbless_db.categories import HTTPResponse, PoolStatus

from limbless_db import PAGE_LIMIT

from .... import db, logger  # noqa
from ....forms.workflows import select_experiment_pools as wff

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

select_experiment_pools_workflow = Blueprint("select_experiment_pools_workflow", __name__, url_prefix="/api/workflows/select_experiment_pools/")


@select_experiment_pools_workflow.route("<int:experiment_id>/begin", methods=["GET"])
@login_required
def begin(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    with DBSession(db) as session:
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        experiment.pools

    form = wff.SelectPoolsForm(experiment=experiment)
    return form.make_response()
    

@select_experiment_pools_workflow.route("<int:experiment_id>/get_pools", methods=["GET"], defaults={"page": 0})
@select_experiment_pools_workflow.route("<int:experiment_id>/get_pools/<int:page>", methods=["GET"])
@login_required
def get_pools(experiment_id: int, page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [PoolStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None
    else:
        status_in = [PoolStatus.ACCEPTED, PoolStatus.STORED]

    pools, n_pages = db.get_pools(
        sort_by=sort_by, descending=descending,
        offset=offset, status_in=status_in
    )

    return make_response(
        render_template(
            "components/tables/select-pools.html", pools=pools, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order, active_page=page,
            status_in=status_in, workflow="select_experiment_pools_workflow",
            context={"experiment_id": experiment.id}
        )
    )


@select_experiment_pools_workflow.route("<int:experiment_id>/query_pools", methods=["POST"])
@login_required
def query_pools(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if (word := request.form.get("name", None)) is not None:
        field_name = "name"
    elif (word := request.form.get("id", None)) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if word is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if field_name == "name":
        pools = db.query_pools(word)
    elif field_name == "id":
        try:
            pools = [db.get_pool(int(word))]
        except ValueError:
            pools = []

    return make_response(
        render_template(
            "components/tables/select-pools.html",
            pools=pools, current_query=word, field_name=field_name,
            context={"experiment_id": experiment.id}, workflow="select_experiment_pools_workflow"
        )
    )
    

@select_experiment_pools_workflow.route("<int:experiment_id>/complete", methods=["POST"])
@login_required
def complete(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    with DBSession(db) as session:
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        experiment.pools
        
    form = wff.SelectPoolsForm(experiment=experiment, formdata=request.form)
    return form.process_request(experiment=experiment)