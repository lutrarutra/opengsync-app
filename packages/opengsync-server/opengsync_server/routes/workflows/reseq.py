from flask import Blueprint, request, Response

from opengsync_db import models
from opengsync_db.categories import AccessType

from ... import db
from ...core import wrappers, exceptions
from ...forms.workflows import reseq as forms
from ...forms import SelectSamplesForm

reseq_workflow = Blueprint("reseq_workflow", __name__, url_prefix="/workflows/reseq/")


def get_context(current_user: models.User, args: dict) -> dict:
    context = {}
    if (seq_request_id := args.get("seq_request_id")) is not None:
        seq_request_id = int(seq_request_id)
        if (seq_request := db.seq_requests.get(seq_request_id)) is None:
            raise exceptions.NotFoundException()
        if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
            raise exceptions.NoPermissionsException()
        context["seq_request"] = seq_request
        
    elif (lab_prep_id := args.get("lab_prep_id")) is not None:
        lab_prep_id = int(lab_prep_id)
        if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
            raise exceptions.NotFoundException()
        context["lab_prep"] = lab_prep

    if not current_user.is_insider():
        if "seq_request" not in context:
            raise exceptions.NoPermissionsException()
        
    return context


@wrappers.htmx_route(reseq_workflow, db=db)
def begin(current_user: models.User) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    context = get_context(current_user, request.args)
        
    form = SelectSamplesForm(
        "reseq", context=context,
        select_libraries=True,
    )
    return form.make_response()


@wrappers.htmx_route(reseq_workflow, db=db, methods=["POST"])
def select(current_user: models.User) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    context = get_context(current_user, request.args)

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

    next_form = forms.ReseqLibrariesForm(form.uuid)
    return next_form.make_response()


@wrappers.htmx_route(reseq_workflow, db=db, methods=["POST"])
def reseq(current_user: models.User, uuid: str) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    return forms.ReseqLibrariesForm(uuid=uuid, formdata=request.form).process_request()