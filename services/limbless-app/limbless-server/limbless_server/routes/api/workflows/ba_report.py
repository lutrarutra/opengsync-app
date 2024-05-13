import json
from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, render_template
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, PoolStatus, LibraryStatus, LibraryType

from .... import db, logger  # noqa
from ....forms.workflows import ba_report as wff

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

ba_report_workflow = Blueprint("ba_report_workflow", __name__, url_prefix="/api/workflows/ba_report/")


@ba_report_workflow.route("get_pools", methods=["GET"], defaults={"page": 0})
@ba_report_workflow.route("get_pools/<int:page>", methods=["GET"])
@login_required
def get_pools(page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [PoolStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None
    else:
        status_in = [PoolStatus.ACCEPTED, PoolStatus.RECEIVED]

    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page
    
    pools, n_pages = db.get_pools(
        sort_by=sort_by, descending=descending, offset=offset, status_in=status_in, experiment_id=experiment_id
    )
    return make_response(
        render_template(
            "components/tables/select-pools.html",
            pools=pools, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, experiment_id=experiment_id,
            status_in=status_in, context="ba_report_workflow"
        )
    )


@ba_report_workflow.route("query_pools", methods=["GET"])
@login_required
def query_pools():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
    pools: list[models.Pool] = []
    if field_name == "name":
        pools = db.query_pools(word, experiment_id=experiment_id)
    elif field_name == "id":
        try:
            _id = int(word)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if (pool := db.get_pool(pool_id=_id)) is not None:
            if experiment_id in [e.id for e in pool.experiments]:
                pools = [pool]
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [PoolStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None
    
    return make_response(
        render_template(
            "components/tables/select-pools.html",
            experiment_id=experiment_id, pools=pools, status_in=status_in,
            context="ba_report_workflow"
        )
    )


@ba_report_workflow.route("get_libraries", methods=["GET"], defaults={"page": 0})
@ba_report_workflow.route("get_libraries/<int:page>", methods=["GET"])
@login_required
def get_libraries(page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None
    else:
        status_in = [LibraryStatus.ACCEPTED]

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(type_in) == 0:
            type_in = None

    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
    libraries, n_pages = db.get_libraries(
        sort_by=sort_by, descending=descending, offset=offset,
        status_in=status_in, experiment_id=experiment_id,
        type_in=type_in
    )
    return make_response(
        render_template(
            "components/tables/select-libraries.html",
            libraries=libraries, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, status_in=status_in, experiment_id=experiment_id,
            type_in=type_in, context="ba_report_workflow"
        )
    )


@ba_report_workflow.route("query_libraries", methods=["GET"])
@login_required
def query_libraries():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(type_in) == 0:
            type_in = None

    libraries: list[models.Library] = []
    if field_name == "name":
        libraries = db.query_libraries(word, status_in=status_in, type_in=type_in, experiment_id=experiment_id)
    elif field_name == "id":
        try:
            _id = int(word)
            if (library := db.get_library(_id)) is not None:
                libraries = [library]
                if status_in is not None and library.status not in status_in:
                    libraries = []
                if type_in is not None and library.type not in type_in:
                    libraries = []
        except ValueError:
            pass

    return make_response(
        render_template(
            "components/tables/select-libraries.html",
            current_query=word, active_query_field=field_name,
            libraries=libraries, type_in=type_in, status_in=status_in, experiment_id=experiment_id,
            context="ba_report_workflow"
        )
    )


@ba_report_workflow.route("begin", methods=["GET"])
@login_required
def begin():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
        
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            experiment = db.get_experiment(experiment_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    else:
        experiment = None
    
    form = wff.SelectSamplesForm(experiment=experiment)
    return form.make_response()


@ba_report_workflow.route("select", methods=["POST"])
@login_required
def select():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
        
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            experiment = db.get_experiment(experiment_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    else:
        experiment = None

    return wff.SelectSamplesForm(formdata=request.form, experiment=experiment).process_request()


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
