import json

from flask import Blueprint, url_for, render_template, flash, request
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import UserRole, SampleStatus, AccessType

from ... import db, logger, forms, logic
from ...core import wrappers, exceptions


samples_htmx = Blueprint("samples_htmx", __name__, url_prefix="/htmx/samples/")


@wrappers.htmx_route(samples_htmx, db=db)
def get(current_user: models.User):
    return make_response(render_template(**logic.sample.get_table_context(current_user=current_user, request=request)))


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
def browse(current_user: models.User, workflow: str):
    return make_response(render_template(**logic.sample.get_browse_context(current_user=current_user, request=request, workflow=workflow)))


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
