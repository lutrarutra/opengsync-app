from typing import TYPE_CHECKING

import pandas as pd

from flask import Blueprint, request, abort, Response
from flask_login import login_required

from opengsync_db import models, db_session
from opengsync_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms.workflows import reseq as forms
from ....forms import SelectSamplesForm
from ....tools import exceptions

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user  # noqa

reseq_workflow = Blueprint("reseq_workflow", __name__, url_prefix="/api/workflows/reseq/")


def get_context(args: dict) -> dict:
    context = {}
    if (seq_request_id := args.get("seq_request_id")) is not None:
        seq_request_id = int(seq_request_id)
        if (seq_request := db.get_seq_request(seq_request_id)) is None:
            raise exceptions.NotFoundException()
        if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
            affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
            if affiliation is None:
                raise exceptions.NoPermissionsException()
        context["seq_request"] = seq_request
        
    elif (lab_prep_id := args.get("lab_prep_id")) is not None:
        lab_prep_id = int(lab_prep_id)
        if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
            raise exceptions.NotFoundException()
        context["lab_prep"] = lab_prep

    if not current_user.is_insider():
        if "seq_request" not in context:
            return abort(HTTPResponse.FORBIDDEN.id)
        
    return context


@reseq_workflow.route("begin", methods=["GET"])
@db_session(db)
@login_required
def begin() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    try:
        context = get_context(request.args)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    except exceptions.OpenGSyncException as e:
        return abort(e.response.id)
        
    form = SelectSamplesForm(
        "reseq", context=context,
        select_libraries=True,
    )
    return form.make_response()


@reseq_workflow.route("select", methods=["POST"])
@db_session(db)
@login_required
def select() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    try:
        context = get_context(request.args)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    except exceptions.OpenGSyncException as e:
        return abort(e.response.id)

    form = SelectSamplesForm(
        "reseq", formdata=request.form, context=context,
        select_libraries=True,
        select_pools=True,
    )

    if not form.validate():
        return form.make_response()

    form.add_table("library_table", form.library_table.rename(columns={"id": "library_id", "name": "library_name"}))
    if "seq_request" in context:
        form.metadata["seq_request_id"] = context["seq_request"].id
    elif "lab_prep" in context:
        form.metadata["lab_prep_id"] = context["lab_prep"].id
    form.metadata["workflow"] = "reseq"
    form.update_data()

    next_form = forms.ReseqLibrariesForm(form.uuid, previous_form=form)
    return next_form.make_response()


@reseq_workflow.route("reseq/<string:uuid>", methods=["POST"])
@db_session(db)
@login_required
def reseq(uuid: str) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    return forms.ReseqLibrariesForm(uuid=uuid, formdata=request.form).process_request()