from fastapi import APIRouter, Depends, Request

from opengsync_db import models

from ....core import dependencies, responses

router = APIRouter(prefix="/check_barcode_constraints", tags=["check_barcode_constraints"])


@router.get("/begin")
def begin_check_barcode_constraints_workflow(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
):
    """Begin the check barcode constraints workflow."""
    # TODO: Port BarcodeConstraintsForm to FastAPI HTMXForm
    # form = BarcodeConstraintsForm(formdata=None)
    # return form.make_response()
    pass