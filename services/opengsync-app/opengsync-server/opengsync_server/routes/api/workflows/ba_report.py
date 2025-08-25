from typing import Any, Literal

import pandas as pd

from flask import Blueprint, request, Request

from opengsync_db import models
from opengsync_db.categories import PoolStatus, LibraryStatus

from .... import db, logger  # noqa
from ....forms.workflows import ba_report as wff
from ....forms import SelectSamplesForm
from ....core import wrappers, exceptions

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
    if (lab_prep_id := args.get("lab_prep_id")) is not None:
        try:
            lab_prep_id = int(lab_prep_id)
            if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
                raise exceptions.NotFoundException()
            context["lab_prep"] = lab_prep
        except ValueError:
            raise exceptions.BadRequestException()
        
    return context


@wrappers.htmx_route(ba_report_workflow, db=db)
def begin(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    context = get_context(request)
    form = SelectSamplesForm(
        workflow="ba_report", context=context,
        library_status_filter=[LibraryStatus.PREPARING],
        pool_status_filter=[PoolStatus.STORED],
        select_libraries=True,
        select_pools=True if not context.get("lab_prep") else False,
        select_lanes=True if not context.get("lab_prep") else False,
    )
    return form.make_response()


@wrappers.htmx_route(ba_report_workflow, db=db, methods=["POST"])
def select(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    context = get_context(request)
    form: SelectSamplesForm = SelectSamplesForm(
        workflow="ba_report", formdata=request.form, context=context,
    )
    if not form.validate():
        return form.make_response()
    
    metadata: dict[str, Any] = {"workflow": "ba_report"}

    if (experiment := context.get("experiment")) is not None:
        metadata["experiment_id"] = experiment.id
    if (seq_request := context.get("seq_request")) is not None:
        metadata["seq_request_id"] = seq_request.id
    if (pool := context.get("pool")) is not None:
        metadata["pool_id"] = pool.id
    if (lab_prep := context.get("lab_prep")) is not None:
        metadata["lab_prep_id"] = lab_prep.id

    form.metadata = metadata
    dfs = []
    df = form.sample_table
    df["sample_type"] = "sample"
    dfs.append(df)
    df = form.library_table
    df["sample_type"] = "library"
    dfs.append(df)
    df = form.pool_table
    df["sample_type"] = "pool"
    dfs.append(df)
    df = form.lane_table
    df["sample_type"] = "lane"
    dfs.append(df)

    df = pd.concat(dfs, ignore_index=True).reset_index(drop=True)
    df["id"] = df["id"].astype(int)
    form.add_table("sample_table", df)
    form.update_data()

    next_form = wff.UploadBAForm(uuid=form.uuid)
    return next_form.make_response()


@wrappers.htmx_route(ba_report_workflow, db=db, methods=["POST"])
def upload(current_user: models.User, uuid: str, method: Literal["manual", "excel"]):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    return wff.UploadBAForm(uuid=uuid, formdata=request.form | request.files, method=method).process_request(user=current_user)


@wrappers.htmx_route(ba_report_workflow, db=db, methods=["POST"])
def parse_sample_order(current_user: models.User, uuid: str):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    return wff.ParseBAExcelFile(uuid=uuid, formdata=request.form).process_request()


@wrappers.htmx_route(ba_report_workflow, db=db, methods=["POST"])
def complete(current_user: models.User, uuid: str):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    return wff.CompleteBAForm(uuid=uuid, formdata=request.form | request.files).process_request(user=current_user)
