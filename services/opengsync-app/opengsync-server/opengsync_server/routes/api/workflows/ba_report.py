from typing import TYPE_CHECKING, Any

from flask import Blueprint, request, abort, Request

from opengsync_db import models
from opengsync_db.categories import HTTPResponse, PoolStatus, LibraryStatus, SampleStatus

from .... import db, logger, htmx_route  # noqa
from ....forms.workflows import ba_report as wff
from ....forms import SelectSamplesForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

ba_report_workflow = Blueprint("ba_report_workflow", __name__, url_prefix="/api/workflows/ba_report/")


def get_context(request: Request) -> dict:
    if request.method == "GET":
        args = request.args
    elif request.method == "POST":
        args = request.form
    else:
        raise NotImplementedError()
    context = {}
    if (seq_request_id := args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["seq_request"] = seq_request
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    if (experiment_id := args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            if (experiment := db.get_experiment(experiment_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["experiment"] = experiment
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    if (pool_id := args.get("pool_id")) is not None:
        try:
            pool_id = int(pool_id)
            if (pool := db.get_pool(pool_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["pool"] = pool
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    if (lab_prep_id := args.get("lab_prep_id")) is not None:
        try:
            lab_prep_id = int(lab_prep_id)
            if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["lab_prep"] = lab_prep
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    return context


@htmx_route(ba_report_workflow, db=db)
def begin():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    context = get_context(request)
    form = SelectSamplesForm(
        workflow="ba_report", context=context,
        sample_status_filter=[SampleStatus.STORED],
        library_status_filter=[LibraryStatus.PREPARING],
        pool_status_filter=[PoolStatus.STORED],
        select_libraries=True,
        select_pools=True if not context.get("lab_prep") else False,
        select_samples=True if not context.get("lab_prep") else False,
        select_lanes=True if not context.get("lab_prep") else False,
    )
    return form.make_response()


@htmx_route(ba_report_workflow, db=db, methods=["POST"])
def select():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    context = get_context(request)
    form: SelectSamplesForm = SelectSamplesForm(
        workflow="ba_report", formdata=request.form, context=context,
    )
    if not form.validate():
        return form.make_response()
    
    complete_ba_report_form = wff.CompleteBAReportForm(uuid=None)
    metadata: dict[str, Any] = {"workflow": "ba_report"}

    if (experiment := context.get("experiment")) is not None:
        metadata["experiment_id"] = experiment.id
    if (seq_request := context.get("seq_request")) is not None:
        metadata["seq_request_id"] = seq_request.id
    if (pool := context.get("pool")) is not None:
        metadata["pool_id"] = pool.id
    if (lab_prep := context.get("lab_prep")) is not None:
        metadata["lab_prep_id"] = lab_prep.id

    complete_ba_report_form.metadata = metadata
    complete_ba_report_form.add_table("sample_table", form.sample_table)
    complete_ba_report_form.add_table("library_table", form.library_table)
    complete_ba_report_form.add_table("pool_table", form.pool_table)
    complete_ba_report_form.add_table("lane_table", form.lane_table)
    complete_ba_report_form.update_data()
    return complete_ba_report_form.make_response()


@htmx_route(ba_report_workflow, db=db, methods=["POST"])
def complete(uuid: str):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    return wff.CompleteBAReportForm(uuid=uuid, formdata=request.form | request.files).process_request(user=current_user)
