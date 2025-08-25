from typing import Any

from flask import Blueprint, request, Request

from opengsync_db import models
from opengsync_db.categories import PoolStatus, LibraryStatus, SampleStatus

from .... import db
from ....core import wrappers, exceptions
from ....forms.workflows import qubit_measure as wff
from ....forms import SelectSamplesForm

qubit_measure_workflow = Blueprint("qubit_measure_workflow", __name__, url_prefix="/api/workflows/qubit_measure/")


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
            if (seq_request := db.seq_requests.get(seq_request_id)) is None:
                raise exceptions.NotFoundException()
            context["seq_request"] = seq_request
        except ValueError:
            raise exceptions.BadRequestException()
    if (experiment_id := args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            if (experiment := db.experiments.get(experiment_id)) is None:
                raise exceptions.NotFoundException()
            context["experiment"] = experiment
        except ValueError:
            raise exceptions.BadRequestException()
    if (pool_id := args.get("pool_id")) is not None:
        try:
            pool_id = int(pool_id)
            if (pool := db.pools.get(pool_id)) is None:
                raise exceptions.NotFoundException()
            context["pool"] = pool
        except ValueError:
            raise exceptions.BadRequestException()
        
    return context


@wrappers.htmx_route(qubit_measure_workflow, db=db)
def begin(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    context = get_context(request)
    form = SelectSamplesForm(
        workflow="qubit_measure", context=context,
        sample_status_filter=[SampleStatus.STORED],
        library_status_filter=[LibraryStatus.PREPARING],
        pool_status_filter=[PoolStatus.STORED],
        select_lanes=True,
        select_pools=True,
        select_libraries=True,
        select_samples=True,
    )
    return form.make_response()


@wrappers.htmx_route(qubit_measure_workflow, db=db, methods=["POST"])
def select(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    context = get_context(request)
    form: SelectSamplesForm = SelectSamplesForm(workflow="qubit_measure", formdata=request.form, context=context)
    if not form.validate():
        return form.make_response()
    
    complete_qubit_measure_form = wff.CompleteQubitMeasureForm(uuid=None)
    metadata: dict[str, Any] = {"workflow": "qubit_measure"}

    if (experiment := context.get("experiment")) is not None:
        metadata["experiment_id"] = experiment.id
    if (seq_request := context.get("seq_request")) is not None:
        metadata["seq_request_id"] = seq_request.id
    if (pool := context.get("pool")) is not None:
        metadata["pool_id"] = pool.id

    complete_qubit_measure_form.metadata = metadata
    complete_qubit_measure_form.add_table("sample_table", form.sample_table)
    complete_qubit_measure_form.add_table("library_table", form.library_table)
    complete_qubit_measure_form.add_table("pool_table", form.pool_table)
    complete_qubit_measure_form.add_table("lane_table", form.lane_table)
    complete_qubit_measure_form.update_data()
    return complete_qubit_measure_form.make_response()


@wrappers.htmx_route(qubit_measure_workflow, db=db, methods=["POST"])
def complete(current_user: models.User, uuid: str):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
        
    return wff.CompleteQubitMeasureForm(uuid=uuid, formdata=request.form).process_request()