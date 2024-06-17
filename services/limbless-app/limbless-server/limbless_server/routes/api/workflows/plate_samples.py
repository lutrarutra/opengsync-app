from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response, render_template
from flask_login import login_required
from flask_htmx import make_response

from limbless_db import models, PAGE_LIMIT
from limbless_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms.workflows import plate_samples as forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

plate_samples_workflow = Blueprint("plate_samples_workflow", __name__, url_prefix="/api/workflows/plate_samples/")


@plate_samples_workflow.route("get_samples", methods=["GET"], defaults={"page": 0})
@plate_samples_workflow.route("get_samples/<int:page>", methods=["GET"])
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
    
    samples, n_pages = db.get_samples(
        seq_request_id=seq_request_id, offset=offset, sort_by=sort_by, descending=descending
    )

    return make_response(
        render_template(
            "components/tables/select-samples.html",
            samples=samples, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            workflow="plate_samples_workflow",
            context=context
        )
    )


@plate_samples_workflow.route("query_samples", methods=["GET"])
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
            workflow="plate_samples_workflow", context=context
        )
    )


@plate_samples_workflow.route("begin", methods=["GET"])
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


@plate_samples_workflow.route("select", methods=["POST"])
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
    
    form = forms.SelectSamplesForm(
        formdata=request.form, seq_request=seq_request
    )
    return form.process_request()