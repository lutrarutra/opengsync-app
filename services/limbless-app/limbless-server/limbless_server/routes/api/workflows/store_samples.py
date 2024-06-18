import json
from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response, render_template
from flask_login import login_required
from flask_htmx import make_response

from limbless_db import models, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, SampleStatus, LibraryStatus, LibraryType, PoolStatus

from .... import db, logger  # noqa
from ....forms.workflows import store_samples as forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

store_samples_workflow = Blueprint("store_samples_workflow", __name__, url_prefix="/api/workflows/store_samples/")


@store_samples_workflow.route("get_samples", methods=["GET"], defaults={"page": 0})
@store_samples_workflow.route("get_samples/<int:page>", methods=["GET"])
@login_required
def get_samples(page: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    context = {}

    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            context["seq_request_id"] = seq_request_id
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SampleStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None
    if status_in is None:
        status_in = [SampleStatus.ACCEPTED]
    
    samples, n_pages = db.get_samples(
        seq_request_id=seq_request_id, status_in=status_in, offset=offset, sort_by=sort_by, descending=descending
    )

    return make_response(
        render_template(
            "components/tables/select-samples.html",
            samples=samples, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            workflow="store_samples_workflow",
            context=context, status_in=status_in
        )
    )


@store_samples_workflow.route("query_samples", methods=["GET"])
@login_required
def query_samples() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    context = {}
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            context["seq_request_id"] = seq_request_id
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)

    samples: list[models.Sample] = []

    if field_name == "name":
        samples = db.query_samples(word=word, seq_request_id=seq_request_id)
    elif field_name == "id":
        try:
            sample_id = int(word)
            if (sample := db.get_sample(sample_id)) is not None:
                samples.append(sample)
        except ValueError:
            pass
        
    return make_response(
        render_template(
            "components/tables/select-samples.html",
            samples=samples, acitve_query_field=field_name, active_query_word=word,
            workflow="store_samples_workflow", context=context
        )
    )


@store_samples_workflow.route("get_libraries", methods=["GET"], defaults={"page": 0})
@store_samples_workflow.route("get_libraries/<int:page>", methods=["GET"])
@login_required
def get_libraries(page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page
    context = {}

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
            context["experiment_id"] = experiment_id
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
            sort_by=sort_by, sort_order=sort_order, status_in=status_in, context=context,
            type_in=type_in, workflow="store_samples_workflow"
        )
    )


@store_samples_workflow.route("query_libraries", methods=["GET"])
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
    
    context = {}
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            context["experiment_id"] = experiment_id
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
            libraries=libraries, type_in=type_in, status_in=status_in, context=context,
            workflow="store_samples_workflow"
        )
    )


@store_samples_workflow.route("get_pools", methods=["GET"], defaults={"page": 0})
@store_samples_workflow.route("get_pools/<int:page>", methods=["GET"])
@login_required
def get_pools(page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    context = {}
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            context["experiment_id"] = experiment_id
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
        status_in = [PoolStatus.ACCEPTED]

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
            sort_by=sort_by, sort_order=sort_order, context=context,
            status_in=status_in, workflow="store_samples_workflow"
        )
    )


@store_samples_workflow.route("query_pools", methods=["GET"])
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
    
    context = {}
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            context["experiment_id"] = experiment_id
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
            context=context, pools=pools, status_in=status_in,
            workflow="store_samples_workflow"
        )
    )


@store_samples_workflow.route("begin", methods=["GET"])
@login_required
def begin() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    else:
        seq_request = None
        
    form = forms.SelectSamplesForm(seq_request=seq_request)
    return form.make_response()


@store_samples_workflow.route("select", methods=["POST"])
@login_required
def select() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    else:
        seq_request = None
    
    form = forms.SelectSamplesForm(formdata=request.form, seq_request=seq_request)
    return form.process_request()


@store_samples_workflow.route("store", methods=["POST"])
@login_required
def store() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    else:
        seq_request = None
    
    form = forms.StoreSamplesForm(seq_request=seq_request, formdata=request.form)
    return form.process_request(user=current_user)