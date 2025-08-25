from datetime import datetime

from flask import Blueprint, request, Response, flash, url_for
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import SampleStatus, LibraryStatus, PoolStatus, SeqRequestStatus, SubmissionType

from .... import db, logger
from ....core import wrappers, exceptions
from ....forms import SelectSamplesForm

store_samples_workflow = Blueprint("store_samples_workflow", __name__, url_prefix="/api/workflows/store_samples/")


@wrappers.htmx_route(store_samples_workflow, db=db)
def begin(current_user: models.User) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    context = {}
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.seq_requests.get(seq_request_id)) is None:
                raise exceptions.NotFoundException()
            context["seq_request"] = seq_request
        except ValueError:
            raise exceptions.BadRequestException()
        
    form = SelectSamplesForm.create_workflow_form("store_samples", context=context)
    return form.make_response()


@wrappers.htmx_route(store_samples_workflow, db=db, methods=["POST"])
def select(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    context = {}
    if (seq_request_id := request.form.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.seq_requests.get(seq_request_id)) is None:
                raise exceptions.NotFoundException()
            context["seq_request"] = seq_request
        except ValueError:
            raise exceptions.BadRequestException()
    else:
        seq_request = None

    form: SelectSamplesForm = SelectSamplesForm(workflow="store_samples", context=context, formdata=request.form)
    
    if not form.validate():
        return form.make_response()

    check_request_ids = []
    for i, row in form.sample_table.iterrows():
        if (sample := db.samples.get(row["id"])) is None:
            logger.error(f"Sample {row['id']} not found")
            raise ValueError(f"Sample {row['id']} not found")
            
        sample.status = SampleStatus.STORED
        sample.timestamp_stored_utc = datetime.now()
        for library_link in sample.library_links:
            if library_link.library.seq_request.status == SeqRequestStatus.ACCEPTED:
                if library_link.library.seq_request.id not in check_request_ids:
                    check_request_ids.append(library_link.library.seq_request.id)
        db.samples.update(sample)

    for i, row in form.library_table.iterrows():
        if (library := db.libraries.get(row["id"])) is None:
            logger.error(f"Library {row['id']} not found")
            raise ValueError(f"Library {row['id']} not found")
        
        if library.seq_request_id not in check_request_ids:
            check_request_ids.append(library.seq_request_id)
        
        if library.is_pooled():
            library.status = LibraryStatus.POOLED
        else:
            library.status = LibraryStatus.STORED
        
        library.timestamp_stored_utc = datetime.now()
        db.libraries.update(library)

    for i, row in form.pool_table.iterrows():
        if (pool := db.pools.get(row["id"])) is None:
            logger.error(f"Pool {row['id']} not found")
            raise ValueError(f"Pool {row['id']} not found")
        
        if pool.seq_request_id is not None and pool.seq_request_id not in check_request_ids:
            check_request_ids.append(pool.seq_request_id)

        pool.status = PoolStatus.STORED
        pool.timestamp_stored_utc = datetime.now()
        db.pools.update(pool)

    for _srid in check_request_ids:
        if (seq_request := db.seq_requests.get(_srid)) is None:
            logger.error(f"SeqRequest {_srid} not found")
            raise Exception(f"SeqRequest {_srid} not found")
        
        if seq_request.submission_type == SubmissionType.RAW_SAMPLES:
            all_samples_stored = True
            for sample in seq_request.samples:
                all_samples_stored = sample.status >= SampleStatus.STORED and all_samples_stored
                if not all_samples_stored:
                    break
            if all_samples_stored:
                seq_request.status = SeqRequestStatus.SAMPLES_RECEIVED
                db.seq_requests.update(seq_request)

        elif seq_request.submission_type == SubmissionType.POOLED_LIBRARIES:
            all_pools_stored = True
            for pool in seq_request.pools:
                all_pools_stored = pool.status >= PoolStatus.STORED and all_pools_stored
                if not all_pools_stored:
                    break
            if all_pools_stored:
                seq_request.status = SeqRequestStatus.PREPARED
                db.seq_requests.update(seq_request)

        elif seq_request.submission_type == SubmissionType.UNPOOLED_LIBRARIES:
            all_libraries_stored = True
            for library in seq_request.libraries:
                all_libraries_stored = library.status >= LibraryStatus.STORED and all_libraries_stored
                if not all_libraries_stored:
                    break
            if all_libraries_stored:
                seq_request.status = SeqRequestStatus.SAMPLES_RECEIVED
                db.seq_requests.update(seq_request)

    flash("Samples Stored!", "success")
    if seq_request is not None:
        return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=seq_request.id))
    
    return make_response(redirect=url_for("dashboard"))