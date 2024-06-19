from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response
from flask_login import login_required

from limbless_db import models
from limbless_db.categories import HTTPResponse, SampleStatus, LibraryStatus, PoolStatus

from .... import db, logger  # noqa
from ....forms.workflows import plate_samples as forms
from ....forms import SelectSamplesForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

plate_samples_workflow = Blueprint("plate_samples_workflow", __name__, url_prefix="/api/workflows/plate_samples/")


@plate_samples_workflow.route("begin", methods=["GET"])
@login_required
def begin() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    context = {}
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["seq_request"] = seq_request
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    form = SelectSamplesForm(
        workflow="plate_samples", context=context,
        sample_status_filter=[SampleStatus.STORED],
        library_status_filter=[LibraryStatus.STORED],
        pool_status_filter=[PoolStatus.STORED]
    )
    return form.make_response()


@plate_samples_workflow.route("select", methods=["POST"])
@login_required
def select():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    context = {}
    if (seq_request_id := request.form.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["seq_request"] = seq_request
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    else:
        seq_request = None
    
    form = SelectSamplesForm(workflow="plate_samples", context=context, formdata=request.form)
    
    if not form.validate():
        return form.make_response()
    
    sample_table, library_table, pool_table = form.get_tables()

    plate_samples_form = forms.PlateSamplesForm(seq_request=seq_request)
    plate_samples_form.metadata = {"workflow": "plate_samples"}
    if seq_request is not None:
        plate_samples_form.metadata["seq_request_id"] = seq_request.id  # type: ignore
    plate_samples_form.add_table("sample_table", sample_table)
    plate_samples_form.add_table("library_table", library_table)
    plate_samples_form.add_table("pool_table", pool_table)
    plate_samples_form.update_data()
    
    plate_samples_form.prepare()
    return plate_samples_form.make_response()


@plate_samples_workflow.route("submit", methods=["POST"])
@login_required
def submit():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    context = {}
    if (seq_request_id := request.form.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["seq_request"] = seq_request
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    else:
        seq_request = None
    
    form = forms.PlateSamplesForm(seq_request=seq_request, formdata=request.form)
    return form.process_request(user=current_user)