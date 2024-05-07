from typing import TYPE_CHECKING, Optional

from flask import Blueprint, request, abort, render_template
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, PoolStatus, LibraryStatus

from .... import db, logger  # noqa
from ....forms.workflows import qubit_measure as wff

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

qubit_measure_workflow = Blueprint("qubit_measure_workflow", __name__, url_prefix="/api/workflows/qubit_measure/")


@qubit_measure_workflow.route("get_pools", methods=["GET"], defaults={"page": 0})
@qubit_measure_workflow.route("get_pools/<int:page>", methods=["GET"])
@login_required
def get_pools(page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)

    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page
    
    pools, n_pages = db.get_pools(sort_by=sort_by, descending=descending, offset=offset, status_in=[PoolStatus.ACCEPTED, PoolStatus.RECEIVED], experiment_id=experiment_id)
    return make_response(
        render_template(
            "workflows/qubit_measure/select-pools-table.html",
            pools=pools, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, experiment_id=experiment_id
        )
    )


@qubit_measure_workflow.route("table_query/<string:field_name>", methods=["POST"])
@login_required
def pools_table_query(field_name: str):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (word := request.form.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
    if field_name == "name":
        pools = db.query_pools(word, experiment_id=experiment_id)
    elif field_name == "id":
        try:
            _id = int(word)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        pools = []
        if (pool := db.get_pool(pool_id=_id)) is not None:
            if experiment_id in [e.id for e in pool.experiments]:
                pools = [pool]
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    return make_response(
        render_template(
            "workflows/qubit_measure/select-pools-table.html",
            pools=pools, n_pages=1, active_page=0, experiment_id=experiment_id
        )
    )


@qubit_measure_workflow.route("get_libraries/<int:page>", methods=["GET"])
@login_required
def get_libraries(page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page
    
    libraries, n_pages = db.get_libraries(status=LibraryStatus.ACCEPTED, sort_by=sort_by, descending=descending, offset=offset)
    return make_response(
        render_template(
            "workflows/qubit_measure/select-libraries-table.html",
            libraries=libraries, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order
        )
    )


@qubit_measure_workflow.route("table_query/<string:field_name>", methods=["POST"])
@login_required
def libraries_table_query(field_name: str):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (word := request.form.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if field_name == "name":
        libraries = db.query_libraries(word, status=LibraryStatus.ACCEPTED)
    elif field_name == "id":
        try:
            _id = int(word)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        libraries = [db.get_library(library_id=_id)]
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    return make_response(
        render_template(
            "workflows/qubit_measure/select-libraries-table.html",
            libraries=libraries, n_pages=1, active_page=0,
        )
    )


@qubit_measure_workflow.route("begin", methods=["GET"], defaults={"experiment_id": None})
@qubit_measure_workflow.route("begin/<int:experiment_id>", methods=["GET"])
@login_required
def begin(experiment_id: Optional[int]):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
        
    if experiment_id is not None:
        if (experiment := db.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        form = wff.SelectSamplesForm(experiment=experiment)
    else:
        form = wff.SelectSamplesForm()

    return form.make_response()


@qubit_measure_workflow.route("select", methods=["POST"])
@login_required
def select():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment_id := request.form.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            experiment = db.get_experiment(experiment_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    return wff.SelectSamplesForm(formdata=request.form, experiment=experiment).process_request()


@qubit_measure_workflow.route("complete", methods=["POST"])
@login_required
def complete():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
        
    return wff.CompleteQubitMeasureForm(formdata=request.form).process_request()