import pandas as pd

from flask import Blueprint, request, abort, Response

from opengsync_db import models
from opengsync_db.categories import HTTPResponse

from .... import db, logger
from ....core import wrappers
from ....forms.workflows import relib as forms
from ....forms import SelectSamplesForm
from ....core import exceptions

relib_workflow = Blueprint("relib_workflow", __name__, url_prefix="/api/workflows/relib/")


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
        return abort(HTTPResponse.FORBIDDEN.id)
    try:
        context = get_context(request.args)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    except exceptions.OpeNGSyncServerException as e:
        return abort(e.response.id)
        
    form = SelectSamplesForm("relib", context=context, select_libraries=True)
    return form.make_response()


@wrappers.htmx_route(relib_workflow, db=db, methods=["POST"])
def select(current_user: models.User) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    try:
        context = get_context(request.args)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    except exceptions.OpeNGSyncServerException as e:
        return abort(e.response.id)

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
        "library_type": [],
        "assay_type": [],
        "genome": [],
        "nuclei_isolation": []
    }
    for library in form.get_libraries():
        data["library_id"].append(library.id)
        data["sample_name"].append(library.sample_name)
        data["library_name"].append(library.name)
        data["library_type"].append(library.type.display_name)
        data["assay_type"].append(library.assay_type.display_name)
        data["genome"].append(library.genome_ref.display_name)
        data["nuclei_isolation"].append("Yes" if library.nuclei_isolation else "No")

    df = pd.DataFrame(data)

    form.add_table("library_table", df)
    form.metadata["workflow"] = "relib"
    form.update_data()

    next_form = forms.LibraryTableForm(
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
        return abort(HTTPResponse.FORBIDDEN.id)
    
    try:
        context = get_context(request.args)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    except exceptions.OpeNGSyncServerException as e:
        return abort(e.response.id)

    return forms.LibraryTableForm(
        seq_request=context.get("seq_request"),
        lab_prep=context.get("lab_prep"),
        pool=context.get("pool"),
        uuid=uuid, formdata=request.form,
    ).process_request()