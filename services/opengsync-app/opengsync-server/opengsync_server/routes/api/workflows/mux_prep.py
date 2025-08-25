from flask import Blueprint, request

from opengsync_db import models
from opengsync_db.categories import MUXType

from .... import db
from ....core import wrappers, exceptions
from ....forms.workflows import mux_prep as forms

mux_prep_workflow = Blueprint("mux_prep_workflow", __name__, url_prefix="/api/workflows/multiplexing_prep/")


@wrappers.htmx_route(mux_prep_workflow, db=db)
def begin(current_user: models.User, lab_prep_id: int, mux_type_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if not (mux_type := MUXType.get(mux_type_id)):
        raise exceptions.BadRequestException()
    
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        raise exceptions.NotFoundException()
    
    if mux_type == MUXType.TENX_OLIGO:
        form = forms.OligoMuxForm(lab_prep=lab_prep)
    elif mux_type == MUXType.TENX_FLEX_PROBE:
        form = forms.FlexMuxForm(lab_prep=lab_prep)
    elif mux_type == MUXType.TENX_ON_CHIP:
        form = forms.OCMMuxForm(lab_prep=lab_prep)
    else:
        raise NotImplementedError(f"Multiplexing type {mux_type} is not implemented.")

    return form.make_response()


@wrappers.htmx_route(mux_prep_workflow, db=db, methods=["GET", "POST"])
def sample_pooling(lab_prep_id: int):
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        return forms.SamplePoolingForm(lab_prep=lab_prep).make_response()

    return forms.SamplePoolingForm(lab_prep=lab_prep, formdata=request.form).process_request()


@wrappers.htmx_route(mux_prep_workflow, db=db, methods=["POST"])
def parse_oligo_mux_annotation(lab_prep_id: int, uuid: str):
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        raise exceptions.NotFoundException()

    return forms.OligoMuxForm(uuid=uuid, lab_prep=lab_prep, formdata=request.form).process_request()


@wrappers.htmx_route(mux_prep_workflow, db=db, methods=["POST"])
def parse_flex_annotation(lab_prep_id: int, uuid: str):
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        raise exceptions.NotFoundException()

    return forms.FlexMuxForm(uuid=uuid, lab_prep=lab_prep, formdata=request.form).process_request()


@wrappers.htmx_route(mux_prep_workflow, db=db, methods=["POST"])
def parse_flex_abc_annotation(lab_prep_id: int, uuid: str):
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        raise exceptions.NotFoundException()

    return forms.FlexABCForm(uuid=uuid, lab_prep=lab_prep, formdata=request.form).process_request()


@wrappers.htmx_route(mux_prep_workflow, db=db, methods=["POST"])
def parse_ocm_annotation(lab_prep_id: int, uuid: str):
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        raise exceptions.NotFoundException()

    return forms.OCMMuxForm(uuid=uuid, lab_prep=lab_prep, formdata=request.form).process_request()