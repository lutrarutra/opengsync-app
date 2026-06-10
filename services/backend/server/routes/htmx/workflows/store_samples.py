from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import models

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/store_samples", tags=["store_samples"])


@router.get("/begin")
async def begin_store_samples_workflow(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
    seq_request_id: int | None = Query(default=None),
):
    """Begin the store samples workflow."""
    # TODO: Port SelectSamplesForm to FastAPI HTMXForm
    # context = {}
    # if seq_request_id is not None:
    #     seq_request = await session.first(Q.seq_request.select(id=seq_request_id))
    #     if seq_request is None:
    #         raise exc.NotFoundException()
    #     context["seq_request"] = seq_request
    # form = SelectSamplesForm.create_workflow_form("store_samples", context=context)
    # return await form.make_response()
    pass