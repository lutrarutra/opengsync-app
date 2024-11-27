from datetime import datetime
from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response, flash, url_for
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse, SampleStatus, LibraryStatus, PoolStatus

from .... import db, logger  # noqa
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

    for i, row in form.sample_table.iterrows():
        if (sample := db.get_sample(row["id"])) is None:
            logger.error(f"Sample {row['id']} not found")
            raise ValueError(f"Sample {row['id']} not found")
            
        sample.status = SampleStatus.STORED
        sample.timestamp_stored_utc = datetime.now()
        sample = db.update_sample(sample)

    for i, row in form.library_table.iterrows():
        if (library := db.get_library(row["id"])) is None:
            logger.error(f"Library {row['id']} not found")
            raise ValueError(f"Library {row['id']} not found")
        
        if library.is_pooled():
            library.status = LibraryStatus.POOLED
        else:
            library.status = LibraryStatus.STORED
        
        library.timestamp_stored_utc = datetime.now()
        library = db.update_library(library)

    for i, row in form.pool_table.iterrows():
        if (pool := db.get_pool(row["id"])) is None:
            logger.error(f"Pool {row['id']} not found")
            raise ValueError(f"Pool {row['id']} not found")
        
        pool.status = PoolStatus.STORED
        pool.timestamp_stored_utc = datetime.now()
        pool = db.update_pool(pool)

    flash("Samples Stored!", "success")
    if seq_request is not None:
        return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id))
    
    return make_response(redirect=url_for("index_page"))