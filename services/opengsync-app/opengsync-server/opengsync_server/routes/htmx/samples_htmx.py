import json

from flask import Blueprint, url_for, render_template, flash, request
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import UserRole, SampleStatus, AccessType, LibraryStatus, LibraryType

from ... import db, logger, forms, logic
from ...core import wrappers, exceptions


samples_htmx = Blueprint("samples_htmx", __name__, url_prefix="/htmx/samples/")


@wrappers.htmx_route(samples_htmx, db=db)
def get(current_user: models.User):
    return make_response(render_template(**logic.tables.render_sample_table(current_user=current_user, request=request)))


@wrappers.htmx_route(samples_htmx, db=db, methods=["DELETE"])
def delete(current_user: models.User, sample_id: int):
    if (sample := db.samples.get(sample_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.samples.get_access_type(sample, current_user)

    if not sample.is_editable() and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
    
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    db.samples.delete(sample_id)

    logger.info(f"Deleted sample {sample.name} (id: {sample.id})")
    flash(f"Deleted sample {sample.name} (id: {sample.id})", "success")

    return make_response(
        redirect=url_for(
            "samples_page.samples"
        ),
    )


@wrappers.htmx_route(samples_htmx, db=db, methods=["GET", "POST"])
def edit(current_user: models.User, sample_id: int):
    if (sample := db.samples.get(sample_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.samples.get_access_type(sample, current_user)

    if not sample.is_editable() and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()

    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    if request.method == "GET":
        return forms.models.SampleForm(sample).make_response()
    
    return forms.models.SampleForm(sample, request.form).process_request()


@wrappers.htmx_route(samples_htmx, db=db, methods=["POST"])
def query(current_user: models.User):
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name)) is None:
        raise exceptions.BadRequestException()

    if current_user.role == UserRole.CLIENT:
        _user_id = current_user.id
    else:
        _user_id = None

    results = db.samples.query(word, user_id=_user_id)

    return make_response(
        render_template(
            "components/search/sample.html",
            results=results,
            field_name=field_name
        )
    )


@wrappers.htmx_route(samples_htmx, db=db)
def browse(current_user: models.User, workflow: str, page: int = 0):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    context = {}

    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            context["seq_request_id"] = seq_request_id
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (pool_id := request.args.get("pool_id")) is not None:
        try:
            pool_id = int(pool_id)
            if (pool := db.pools.get(pool_id)) is None:
                raise exceptions.NotFoundException()
            context["pool_id"] = pool.id
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SampleStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None

    samples, n_pages = db.samples.find(
        seq_request_id=seq_request_id, status_in=status_in, page=page, sort_by=sort_by, descending=descending,
        pool_id=pool_id
    )
    context["workflow"] = workflow
    return make_response(
        render_template(
            "components/tables/select-samples.html",
            samples=samples, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            workflow=workflow, context=context, status_in=status_in
        )
    )


@wrappers.htmx_route(samples_htmx, db=db)
def browse_query(current_user: models.User, workflow: str):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        raise exceptions.BadRequestException()
    
    context = {}
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            context["seq_request_id"] = seq_request_id
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (pool_id := request.args.get("pool_id")) is not None:
        try:
            pool_id = int(pool_id)
            if (pool := db.pools.get(pool_id)) is None:
                raise exceptions.NotFoundException()
            context["pool_id"] = pool.id
        except ValueError:
            raise exceptions.BadRequestException()

    samples: list[models.Sample] = []

    if field_name == "name":
        samples = db.samples.query(word=word, seq_request_id=seq_request_id, pool_id=pool_id)
    elif field_name == "id":
        try:
            sample_id = int(word)
            if (sample := db.samples.get(sample_id)) is not None:
                samples.append(sample)
        except ValueError:
            pass
        
    context["workflow"] = workflow
    return make_response(
        render_template(
            "components/tables/select-samples.html",
            samples=samples, acitve_query_field=field_name, active_query_word=word,
            workflow=workflow, context=context
        )
    )


@wrappers.htmx_route(samples_htmx, db=db)
def select_all(current_user: models.User, workflow: str):
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

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SampleStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None

    samples, _ = db.samples.find(
        seq_request_id=seq_request_id, status_in=status_in, limit=None
    )

    form = forms.SelectSamplesForm.create_workflow_form(workflow, context=context, selected_samples=samples)
    return form.make_response(samples=samples)
