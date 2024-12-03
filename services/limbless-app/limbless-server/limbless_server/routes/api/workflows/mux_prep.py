from typing import TYPE_CHECKING, Literal

from flask import Blueprint, request, abort, send_file, current_app, Response
from flask_login import login_required

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms.workflows import mux_prep as forms
from ....forms.MultiStepForm import MultiStepForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

mux_prep_workflow = Blueprint("mux_prep_workflow", __name__, url_prefix="/api/workflows/multiplexing_prep/")


@mux_prep_workflow.route("<int:lab_prep_id>/begin/<string:multiplexing_type>", methods=["GET"])
@login_required
def begin(lab_prep_id: int, multiplexing_type: Literal["cmo", "flex"]):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if multiplexing_type not in ["cmo", "flex"]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if multiplexing_type == "cmo":
        form = forms.CMOMuxForm(lab_prep=lab_prep)
        return form.make_response()
    elif multiplexing_type == "flex":
        form = forms.FlexMuxForm(lab_prep=lab_prep)
        return form.make_response()

    return abort(HTTPResponse.BAD_REQUEST.id)


@mux_prep_workflow.route("<int:lab_prep_id>/parse_cmo_annotation/<string:uuid>", methods=["POST"])
@db_session(db)
@login_required
def parse_cmo_annotation(lab_prep_id: int, uuid: str):
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return forms.CMOMuxForm(uuid=uuid, lab_prep=lab_prep, formdata=request.form).process_request()


@mux_prep_workflow.route("<int:lab_prep_id>/parse_flex_annotation/<string:uuid>", methods=["POST"])
@db_session(db)
@login_required
def parse_flex_annotation(lab_prep_id: int, uuid: str):
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return forms.FlexMuxForm(uuid=uuid, lab_prep=lab_prep, formdata=request.form).process_request()