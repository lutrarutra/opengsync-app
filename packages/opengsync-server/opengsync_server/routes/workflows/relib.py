import pandas as pd

from flask import Blueprint, request, Response

from opengsync_db import models

from ... import db, logger
from ...core import wrappers, exceptions
from ...forms.workflows import relib as forms
from ...forms import SelectSamplesForm

relib_workflow = Blueprint("relib_workflow", __name__, url_prefix="/workflows/relib/")


def get_context(args: dict) -> dict:
    context = {}
    if (seq_request_id := args.get("seq_request_id")) is not None:
        seq_request_id = int(seq_request_id)
        if (seq_request := db.seq_requests.get(seq_request_id)) is None:
            raise exceptions.NotFoundException()
        context["seq_request"] = seq_request
        
    elif (lab_prep_id := args.get("lab_prep_id")) is not None:
        lab_prep_id = int(lab_prep_id)
        if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
            raise exceptions.NotFoundException()
        context["lab_prep"] = lab_prep
        
    return context


@wrappers.htmx_route(relib_workflow, db=db)
def begin(current_user: models.User) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    context = get_context(request.args)
        
    form = SelectSamplesForm("relib", context=context, select_libraries=True)
    return form.make_response()


@wrappers.htmx_route(relib_workflow, db=db, methods=["POST"])
def select(current_user: models.User) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    context = get_context(request.args)

    form = SelectSamplesForm(
        "relib", formdata=request.form, context=context,
        select_libraries=True,
        select_pools=True,
    )

    if not form.validate():
        return form.make_response()

    data = {
        "library_id": [],
        "sample_name": [],
        "library_name": [],
        "library_type_id": [],
        "service_type_id": [],
        "genome_id": [],
        "nuclei_isolation": []
    }
    for library in form.get_libraries():
        data["library_id"].append(library.id)
        data["sample_name"].append(library.sample_name)
        data["library_name"].append(library.name)
        data["library_type_id"].append(library.type.id)
        data["service_type_id"].append(library.service_type.id)
        data["genome_id"].append(library.genome_ref.id)
        data["nuclei_isolation"].append("Yes" if library.nuclei_isolation else "No")

    df = pd.DataFrame(data)

    form.tables["library_table"] = df
    form.metadata["workflow"] = "relib"
    form.step()

    next_form = forms.LibraryEditTableForm(
        seq_request=context.get("seq_request"),
        lab_prep=context.get("lab_prep"),
        pool=context.get("pool"),
        formdata=None,
        uuid=form.uuid,
    )
    return next_form.make_response()


@wrappers.htmx_route(relib_workflow, db=db, methods=["POST"])
def parse_library_type_form(current_user: models.User, uuid: str) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    context = get_context(request.args)

    return forms.LibraryEditTableForm(
        seq_request=context.get("seq_request"),
        lab_prep=context.get("lab_prep"),
        pool=context.get("pool"),
        uuid=uuid, formdata=request.form,
    ).process_request()