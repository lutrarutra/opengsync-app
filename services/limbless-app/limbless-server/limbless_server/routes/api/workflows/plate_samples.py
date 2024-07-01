from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response
from flask_login import login_required

import pandas as pd

from limbless_db import models, DBSession
from limbless_db.categories import HTTPResponse

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
        
    if (pool_id := request.args.get("pool_id")) is not None:
        with DBSession(db) as session:
            try:
                pool_id = int(pool_id)
                if (pool := session.get_pool(pool_id)) is None:
                    return abort(HTTPResponse.NOT_FOUND.id)
                context["pool"] = pool
            except ValueError:
                return abort(HTTPResponse.BAD_REQUEST.id)
            
            library_data = {
                "id": [], "name": [], "status_id": [],
            }
            for library in pool.libraries:
                library_data["id"].append(library.id)
                library_data["name"].append(library.name)
                library_data["status_id"].append(library.status_id)

        plate_samples_form = forms.PlateSamplesForm(context=context)
        plate_samples_form.metadata = {"workflow": "plate_samples", "pool_id": pool.id}
        plate_samples_form.add_table("sample_table", pd.DataFrame(columns=["id", "name", "status_id"]))
        plate_samples_form.add_table("library_table", pd.DataFrame(library_data))
        plate_samples_form.add_table("pool_table", pd.DataFrame(columns=["id", "name", "status_id"]))
        plate_samples_form.update_data()
        
        plate_samples_form.prepare()
        return plate_samples_form.make_response()
        
    form = SelectSamplesForm.create_workflow_form("plate_samples", context=context)
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
    
    form = SelectSamplesForm.create_workflow_form("plate_samples", context=context, formdata=request.form)
    
    if not form.validate():
        return form.make_response()
    
    sample_table, library_table, pool_table, _ = form.get_tables()

    plate_samples_form = forms.PlateSamplesForm(context=context)
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
    
    logger.debug(request.form)
    
    context = {}
    if (seq_request_id := request.form.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["seq_request"] = seq_request
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)

    if (pool_id := request.form.get("pool_id")) is not None:
        with DBSession(db) as session:
            try:
                pool_id = int(pool_id)
                if (pool := session.get_pool(pool_id)) is None:
                    return abort(HTTPResponse.NOT_FOUND.id)
                context["pool"] = pool
            except ValueError:
                return abort(HTTPResponse.BAD_REQUEST.id)
    
    form = forms.PlateSamplesForm(context=context, formdata=request.form)
    return form.process_request(user=current_user)