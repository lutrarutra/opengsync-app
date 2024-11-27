from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response
from flask_login import login_required

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms.workflows import store_samples as forms
from ....forms import SelectSamplesForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

store_samples_workflow = Blueprint("store_samples_workflow", __name__, url_prefix="/api/workflows/store_samples/")


@store_samples_workflow.route("begin", methods=["GET"])
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
        
    form = SelectSamplesForm.create_workflow_form("store_samples", context=context)
    return form.make_response()


@store_samples_workflow.route("select", methods=["POST"])
@db_session(db)
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

    form: SelectSamplesForm = SelectSamplesForm(workflow="store_samples", context=context, formdata=request.form)
    
    if not form.validate():
        return form.make_response()

    store_samples_form = forms.StoreSamplesForm(seq_request=seq_request, uuid=None)
    store_samples_form.metadata = {"workflow": "store_samples"}
    if seq_request is not None:
        store_samples_form.metadata["seq_request_id"] = seq_request.id  # type: ignore
    store_samples_form.add_table("sample_table", form.sample_table)
    store_samples_form.add_table("library_table", form.library_table)
    store_samples_form.add_table("pool_table", form.pool_table)
    store_samples_form.update_data()
    
    store_samples_form.prepare()
    return store_samples_form.make_response()


@store_samples_workflow.route("submit/<string:uuid>", methods=["POST"])
@login_required
def submit(uuid: str) -> Response:
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

    form = forms.StoreSamplesForm(uuid=uuid, seq_request=seq_request, formdata=request.form)
    return form.process_request(user=current_user)