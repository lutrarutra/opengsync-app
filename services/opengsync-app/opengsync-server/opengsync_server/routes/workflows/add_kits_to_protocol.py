from flask import Blueprint, request

from opengsync_db import models

from ... import db, logger, forms  # noqa
from ...forms.workflows import lane_pools as wff
from ...core import wrappers, exceptions

add_kits_to_protocol_workflow = Blueprint("add_kits_to_protocol_workflow", __name__, url_prefix="/workflows/add_kits_to_protocol/")

@wrappers.htmx_route(add_kits_to_protocol_workflow, db=db)
def begin(current_user: models.User, protocol_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (protocol := db.protocols.get(protocol_id)) is None:
        raise exceptions.NotFoundException()

    form = forms.workflows.add_protocol_kits.AddKitCombinationsFrom(formdata=request.form, protocol=protocol)
    return form.make_response()

@wrappers.htmx_route(add_kits_to_protocol_workflow, db=db, methods=["POST"])
def add_kit_combinations(current_user: models.User, protocol_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (protocol := db.protocols.get(protocol_id)) is None:
        raise exceptions.NotFoundException()

    form = forms.workflows.add_protocol_kits.AddKitCombinationsFrom(formdata=request.form, protocol=protocol)
    return form.process_request()


