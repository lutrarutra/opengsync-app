import pandas as pd

from flask import Blueprint, request

from opengsync_db import models

from .... import db, logger
from ....core import wrappers, exceptions

check_barcode_constraints_workflow = Blueprint("check_barcode_constraints_workflow", __name__, url_prefix="/api/workflows/check_barcode_constraints/")


@wrappers.htmx_route(check_barcode_constraints_workflow, db=db)
def begin(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    from ....forms.workflows.BarcodeConstraintsForm import BarcodeConstraintsForm
    form = BarcodeConstraintsForm(formdata=None)
    return form.make_response()


@wrappers.htmx_route(check_barcode_constraints_workflow, db=db, methods=["POST"])
def check(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    from ....forms.workflows.BarcodeConstraintsForm import BarcodeConstraintsForm
    form: BarcodeConstraintsForm = BarcodeConstraintsForm(formdata=request.form)
    
    return form.process_request()