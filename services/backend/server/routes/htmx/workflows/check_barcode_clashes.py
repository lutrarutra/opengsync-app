from fastapi import APIRouter, Depends, Request

from opengsync_db import models

from ....core import dependencies, responses

router = APIRouter(prefix="/check_barcode_clashes", tags=["check_barcode_clashes"])


@router.get("/begin")
async def begin_check_barcode_clashes_workflow(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
):
    """Begin the check barcode clashes workflow."""
    # TODO: Port SelectSamplesForm to FastAPI HTMXForm
    # form = SelectSamplesForm(
    #     workflow="check_barcode_clashes",
    #     select_lanes=True,
    #     select_pools=True,
    #     select_libraries=True,
    # )
    # return await form.make_response()
    pass