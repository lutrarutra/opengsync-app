from typing import TYPE_CHECKING

from flask import Blueprint, request, abort
from flask_login import login_required

from opengsync_db import models, db_session
from opengsync_db.categories import HTTPResponse, MUXType

from .... import db, logger, htmx_route  # noqa
from ....forms.workflows import mux_prep as forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

mux_prep_workflow = Blueprint("mux_prep_workflow", __name__, url_prefix="/api/workflows/multiplexing_prep/")


@htmx_route(mux_prep_workflow, "<int:lab_prep_id>/begin/<int:mux_type_id>", db=db)
def begin(lab_prep_id: int, mux_type_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if not (mux_type := MUXType.get(mux_type_id)):
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if mux_type == MUXType.TENX_OLIGO:
        form = forms.OligoMuxForm(lab_prep=lab_prep)
    elif mux_type == MUXType.TENX_FLEX_PROBE:
        form = forms.FlexMuxForm(lab_prep=lab_prep)
    elif mux_type == MUXType.TENX_ON_CHIP:
        form = forms.OCMMuxForm(lab_prep=lab_prep)
    else:
        raise NotImplementedError(f"Multiplexing type {mux_type} is not implemented.")

    return form.make_response()


@htmx_route(mux_prep_workflow, "<int:lab_prep_id>/parse_oligo_mux_annotation/<string:uuid>", db=db, methods=["POST"])
def parse_oligo_mux_annotation(lab_prep_id: int, uuid: str):
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return forms.OligoMuxForm(uuid=uuid, lab_prep=lab_prep, formdata=request.form).process_request()


@htmx_route(mux_prep_workflow, "<int:lab_prep_id>/parse_flex_annotation/<string:uuid>", db=db, methods=["POST"])
def parse_flex_annotation(lab_prep_id: int, uuid: str):
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return forms.FlexMuxForm(uuid=uuid, lab_prep=lab_prep, formdata=request.form).process_request()


@htmx_route(mux_prep_workflow, "<int:lab_prep_id>/parse_flex_abc_annotation/<string:uuid>", db=db, methods=["POST"])
def parse_flex_abc_annotation(lab_prep_id: int, uuid: str):
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return forms.FlexABCForm(uuid=uuid, lab_prep=lab_prep, formdata=request.form).process_request()


@htmx_route(mux_prep_workflow, "<int:lab_prep_id>/parse_ocm_annotation/<string:uuid>", db=db, methods=["POST"])
def parse_ocm_annotation(lab_prep_id: int, uuid: str):
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return forms.OCMMuxForm(uuid=uuid, lab_prep=lab_prep, formdata=request.form).process_request()