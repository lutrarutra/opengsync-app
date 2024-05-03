from typing import TYPE_CHECKING, Optional

from flask import Blueprint, request, abort, render_template
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, PoolStatus, LibraryStatus

from .... import db, logger
from ....forms.workflows import ba_report as wff

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

ba_report_workflow = Blueprint("ba_report_workflow", __name__, url_prefix="/api/workflows/ba_report/")


@ba_report_workflow.route("get_pools/<int:page>", methods=["GET"])
@login_required
def get_pools(page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page
    
    pools, n_pages = db.get_pools(sort_by=sort_by, descending=descending, offset=offset, status=PoolStatus.RECEIVED)
    return make_response(
        render_template(
            "workflows/ba_report/select-pools-table.html",
            pools=pools, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order
        )
    )


@ba_report_workflow.route("table_query/<string:field_name>", methods=["POST"])
@login_required
def pools_table_query(field_name: str):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (word := request.form.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if field_name == "name":
        pools = db.query_pools(word)
    elif field_name == "id":
        try:
            _id = int(word)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        pools = [db.get_pool(pool_id=_id)]
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    return make_response(
        render_template(
            "workflows/ba_report/select-pools-table.html",
            pools=pools, n_pages=1, active_page=0,
        )
    )


@ba_report_workflow.route("get_libraries/<int:page>", methods=["GET"])
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
            "workflows/ba_report/select-libraries-table.html",
            libraries=libraries, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order
        )
    )


@ba_report_workflow.route("table_query/<string:field_name>", methods=["POST"])
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
            "workflows/ba_report/select-libraries-table.html",
            libraries=libraries, n_pages=1, active_page=0,
        )
    )


@ba_report_workflow.route("begin", methods=["GET"], defaults={"experiment_id": None})
@ba_report_workflow.route("begin/<int:experiment_id>", methods=["GET"])
@login_required
def begin(experiment_id: Optional[int]):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
        
    if experiment_id is not None:
        if (experiment := db.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        form = wff.BAInputForm(experiment=experiment)
        form.prepare()
        return form.make_response()
    
    form = wff.SelectSamplesForm()
    return form.make_response()


@ba_report_workflow.route("select", methods=["POST"])
@login_required
def select():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
        
    return wff.SelectSamplesForm(formdata=request.form).process_request()


@ba_report_workflow.route("attach_table", methods=["POST"])
@login_required
def attach_table():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    return wff.BAInputForm(formdata=request.form | request.files).process_request()


@ba_report_workflow.route("qc_pools", methods=["POST"])
@login_required
def qc_pools():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    return wff.CompleteBAReportForm(formdata=request.form).process_request(current_user=current_user)
